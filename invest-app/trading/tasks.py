import logging
from celery import shared_task
from django.core.cache import cache
from .models import AnalyzedStock, TradingAccount
from .analysis.market_scanner import screen_initial_stocks
from .ai_analysis_service import analyze_stock
from .kis_client import KISApiClient

logger = logging.getLogger(__name__)


@shared_task
def run_daily_morning_routine():
    """
    1차: KIS API를 통해 거래량 상위 종목을 조회하고 기본적인 필터링을 거쳐
    AnalyzedStock 모델에 저장합니다.
    """
    logger.info("Celery Task: Starting initial stock screening.")
    screen_initial_stocks()
    logger.info("Celery Task: Initial stock screening finished.")


@shared_task
def analyze_stocks_task():
    """
    2차: 1차 스크리닝된 종목들을 대상으로 AI 분석을 수행하고,
    투자 기간(horizon)과 리스크 관리 기준을 결정하여 DB에 업데이트합니다.
    """
    logger.info("Celery Task: Starting AI stock analysis.")
    cache.set('analysis_progress', {'status': '분석 시작 중...', 'progress': 0}, timeout=300)
    
    first_account = TradingAccount.objects.filter(is_active=True).first()
    if not first_account:
        logger.error("No active trading account found for API calls. Aborting analysis.")
        cache.set('analysis_progress', {'status': '오류: 활성 계좌 없음', 'progress': -1}, timeout=300)
        return

    client = KISApiClient(
        app_key=first_account.app_key,
        app_secret=first_account.app_secret,
        account_no=first_account.account_number,
        account_type=first_account.account_type
    )

    stocks_to_analyze = AnalyzedStock.objects.filter(is_investable=True)
    total_stocks = stocks_to_analyze.count()
    logger.info(f"Found {total_stocks} stocks to analyze.")

    if total_stocks == 0:
        logger.info("No stocks to analyze.")
        cache.set('analysis_progress', {'status': '완료: 분석할 종목 없음', 'progress': 100}, timeout=60)
        return

    for i, stock in enumerate(stocks_to_analyze):
        try:
            analysis_result = analyze_stock(stock.symbol, client)
            if analysis_result:
                stock.investment_horizon = analysis_result.horizon
                stock.raw_analysis_data = {
                    'stop_loss_price': analysis_result.stop_loss_price,
                    'target_price': analysis_result.target_price,
                    **analysis_result.raw_data
                }
                stock.save()
                logger.info(f"Successfully analyzed and updated {stock.symbol}.")
            else:
                logger.warning(f"Analysis for {stock.symbol} did not return a result.")
        except Exception as e:
            logger.error(f"An error occurred during analysis of {stock.symbol}: {e}", exc_info=True)

        progress = int(((i + 1) / total_stocks) * 100)
        status_text = f"분석 중: {stock.stock_name} ({i + 1}/{total_stocks})"
        cache.set('analysis_progress', {'status': status_text, 'progress': progress}, timeout=300)

    logger.info("Celery Task: AI stock analysis finished.")
    cache.set('analysis_progress', {'status': '분석 완료', 'progress': 100}, timeout=60)


from decimal import Decimal
from .models import StrategySettings, Portfolio, TradeLog

@shared_task
def execute_ai_trades_task():
    """
    3차: AI 분석 결과를 바탕으로 포트폴리오 구성 및 실제 매매를 수행합니다.
    """
    logger.info("Celery Task: Starting AI trade execution.")

    # 1. Get strategy settings and active account
    try:
        settings = StrategySettings.objects.first()
        account = TradingAccount.objects.filter(is_active=True).first()
        if not settings or not account:
            logger.error("Strategy settings or active account not found. Aborting trade execution.")
            return
    except Exception as e:
        logger.error(f"Error fetching settings or account: {e}")
        return

    # 2. Initialize API client and get account balance
    client = KISApiClient(app_key=account.app_key, app_secret=account.app_secret, account_no=account.account_number, account_type=account.account_type)
    balance_info_res = client.get_account_balance()
    if not balance_info_res or not balance_info_res.is_ok():
        error_msg = balance_info_res.get_error_message() if balance_info_res else "No response from API."
        logger.error(f"Failed to fetch account balance: {error_msg}")
        return

    balance_info = balance_info_res.get_body()
    output1 = balance_info.get('output1', [{}])[0]
    total_assets = Decimal(output1.get('tot_evlu_amt', '0'))
    cash_available = Decimal(output1.get('dnca_tot_amt', '0'))
    logger.info(f"Total Assets: {total_assets}, Available Cash: {cash_available}")

    # 3. Get current portfolio from our DB
    current_portfolio_symbols = list(Portfolio.objects.filter(account=account, is_open=True).values_list('symbol', flat=True))

    # 4. Identify new trading opportunities
    # Find stocks analyzed today with a clear investment horizon, that are not already in our portfolio
    opportunities = AnalyzedStock.objects.filter(
        investment_horizon__in=['SHORT', 'MID', 'LONG']
    ).exclude(
        symbol__in=current_portfolio_symbols
    ).order_by('-analysis_date', '-last_price') # Simple ordering, can be improved

    if not opportunities:
        logger.info("No new trading opportunities found.")
        return

    logger.info(f"Found {len(opportunities)} new opportunities. Checking against portfolio balance.")

    # 5. Execute trades based on allocation strategy
    # This is a simplified logic. A real-world scenario would be more complex.
    # We'll try to fill one new position if cash is available.
    
    # Define how much of the cash to use for a new position (e.g., 20%)
    TRADE_BUDGET_PER_STOCK = cash_available * Decimal('0.20')

    for opp in opportunities:
        if cash_available < 100000: # Minimum cash threshold to trade
            logger.info("Cash available is below threshold. Halting further trades.")
            break

        stock_price = Decimal(opp.last_price)
        if stock_price <= 0:
            logger.warning(f"Skipping {opp.symbol} due to invalid price: {stock_price}")
            continue

        if TRADE_BUDGET_PER_STOCK > stock_price:
            quantity_to_buy = int(TRADE_BUDGET_PER_STOCK // stock_price)

            logger.info(f"Attempting to buy {quantity_to_buy} shares of {opp.symbol} at {stock_price}.")

            # Place order using the new validated method
            order_response = client.place_order(
                account=account,
                symbol=opp.symbol,
                quantity=quantity_to_buy,
                price=int(stock_price),
                order_type='BUY'
            )

            # The creation of TradeLog and Portfolio is now handled by the place_order method
            # and the post_save signal on the TradeLog model.
            # We just need to check if the order was accepted by the broker.
            if order_response and order_response.get('rt_cd') == '0':
                logger.info(f"AI trade order for {opp.symbol} was successfully sent to the broker.")
                # Reduce cash for next loop iteration to avoid over-ordering in the same run
                cash_available -= (quantity_to_buy * stock_price)
            elif order_response and order_response.get('is_validation_error'):
                logger.warning(f"AI trade for {opp.symbol} failed validation: {order_response.get('msg1')}")
            else:
                logger.error(f"AI trade for {opp.symbol} failed at the broker: {order_response}")

    logger.info("Celery Task: AI trade execution finished.")


@shared_task
def run_all_active_strategies():
    """
    Placeholder task to prevent `KeyError: 'trading.tasks.run_all_active_strategies'`
    This task was likely part of a previous feature and is still in the scheduler's database.
    """
    logger.info("Placeholder task 'run_all_active_strategies' executed. No action taken.")
    pass

@shared_task
def monitor_open_positions_task():
    """
    실시간으로 현재 보유 포지션을 모니터링하고, 손절/익절 조건 도달 시 매도 주문을 실행합니다.
    """
    logger.info("Celery Task: Starting real-time position monitoring.")

    # Get active account
    account = TradingAccount.objects.filter(is_active=True).first()
    if not account:
        logger.warning("No active account for monitoring.")
        return

    # Get open positions
    open_positions = Portfolio.objects.filter(account=account, is_open=True)
    if not open_positions.exists():
        logger.info("No open positions to monitor.")
        return

    logger.info(f"Monitoring {open_positions.count()} open positions.")
    client = KISApiClient(app_key=account.app_key, app_secret=account.app_secret, account_no=account.account_number, account_type=account.account_type)

    for pos in open_positions:
        # Get current price
        price_info = client.get_current_price(pos.symbol)
        if not (price_info and price_info.get('rt_cd') == '0'):
            logger.warning(f"Could not fetch current price for {pos.symbol}. Skipping.")
            continue

        current_price = Decimal(price_info.get('output', {}).get('stck_prpr', '0'))

        if current_price <= 0:
            continue

        # Check stop-loss and target-price
        should_sell = False
        sell_reason = ""
        if current_price <= pos.stop_loss_price:
            should_sell = True
            sell_reason = f"Stop-Loss triggered at {current_price}"
        elif current_price >= pos.target_price:
            should_sell = True
            sell_reason = f"Target-Price triggered at {current_price}"

        if should_sell:
            logger.info(f"Selling {pos.symbol} for account {account.account_name}. Reason: {sell_reason}")

            # Place sell order using the new validated method
            order_response = client.place_order(
                account=account,
                symbol=pos.symbol,
                quantity=pos.quantity,
                price=int(current_price),
                order_type='SELL'
            )

            if order_response and order_response.get('rt_cd') == '0':
                logger.info(f"Monitoring task: Sell order for {pos.symbol} was successfully sent to the broker.")
            elif order_response and order_response.get('is_validation_error'):
                logger.warning(f"Monitoring task: Sell order for {pos.symbol} failed validation: {order_response.get('msg1')}")
            else:
                logger.error(f"Monitoring task: Sell order for {pos.symbol} failed at the broker: {order_response}")

    logger.info("Celery Task: Real-time position monitoring finished.")


# --- WebSocket Data Streaming Task ---
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import websockets
import asyncio

@shared_task
def stream_kis_data_task():
    """
    Connects to the KIS WebSocket server, subscribes to real-time data,
    and broadcasts it to the appropriate Channels groups.
    This task should only have one worker running it.
    """
    logger.info("Attempting to start KIS WebSocket data streamer task.")

    # Use a cache lock to ensure only one instance of this task runs.
    if not cache.add("kis_streamer_lock", "running", timeout=None):
        logger.warning("KIS data streamer task is already running. Exiting.")
        return

    try:
        # This is a long-running task, so we run the async part synchronously.
        async_to_sync(run_streamer)()
    except Exception as e:
        logger.error(f"KIS data streamer task failed: {e}", exc_info=True)
    finally:
        # Remove the lock when the task exits.
        cache.delete("kis_streamer_lock")
        logger.info("KIS data streamer task stopped and lock released.")


async def run_streamer():
    """The core async function for the WebSocket streamer."""
    channel_layer = get_channel_layer()

    # We need an active account to get an approval key
    first_account = await database_sync_to_async(TradingAccount.objects.filter(is_active=True).first)()
    if not first_account:
        logger.error("No active trading account found for KIS stream. Aborting.")
        return

    client = KISApiClient(
        app_key=first_account.app_key,
        app_secret=first_account.app_secret,
        account_no=first_account.account_number,
        account_type=first_account.account_type
    )

    uri = "ws://ops.koreainvestment.com:21000"
    if client.is_simulation:
        uri = "ws://ops.koreainvestment.com:31000"

    approval_key = await database_sync_to_async(client.get_approval_key)()
    if not approval_key:
        logger.error("Failed to get KIS approval key for stream. Aborting.")
        return

    while True: # Main reconnect loop
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                logger.info("KIS streamer connected to WebSocket server.")

                # Subscribe to execution reports for all active accounts
                all_accounts = await database_sync_to_async(list)(TradingAccount.objects.filter(is_active=True))
                for account in all_accounts:
                    await subscribe_to_executions(websocket, approval_key, account, client.is_simulation)

                # Subscribe to prices for all unique stocks in portfolios
                all_symbols = await database_sync_to_async(list)(
                    Portfolio.objects.filter(is_open=True).values_list('symbol', flat=True).distinct()
                )
                for symbol in all_symbols:
                    await subscribe_to_price(websocket, approval_key, symbol)

                # Listen for messages
                async for message in websocket:
                    await handle_stream_message(message, channel_layer, client)

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"KIS streamer connection closed: {e}. Reconnecting in 5 seconds...")
        except Exception as e:
            logger.error(f"Error in KIS streamer: {e}. Reconnecting in 5 seconds...", exc_info=True)

        await asyncio.sleep(5)


async def subscribe_to_executions(websocket, key, account, is_sim):
    tr_id = "H0STCNI9" if is_sim else "H0STCNI0"
    user_id = account.user.username # This might need adjustment based on KIS specs
    subscription_data = {
        "header": {"approval_key": key, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
        "body": {"input": {"tr_id": tr_id, "tr_key": user_id}}
    }
    await websocket.send(json.dumps(subscription_data))
    logger.info(f"Subscribed to execution reports for account {account.account_number}")

async def subscribe_to_price(websocket, key, symbol):
    subscription_data = {
        "header": {"approval_key": key, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
        "body": {"input": {"tr_id": "JEQ", "tr_key": symbol}} # JEQ is for real-time price
    }
    await websocket.send(json.dumps(subscription_data))
    logger.info(f"Subscribed to price updates for symbol {symbol}")


async def handle_stream_message(message, channel_layer, client):
    """Parses messages from KIS and broadcasts them."""
    if message.startswith('{'): # It's a JSON message (likely a response to subscription)
        logger.info(f"KIS stream received JSON message: {message}")
        return

    parts = message.split('|')
    if len(parts) < 2:
        logger.warning(f"Unknown message format from KIS stream: {message}")
        return

    tr_id = parts[1]

    # Handle Price Update
    if tr_id == "JEQ": # Real-time price
        price_data = {
            'type': 'stock_price_update',
            'symbol': parts[2].strip(),
            'price': abs(int(parts[3])),
            'volume': int(parts[12]),
        }
        await channel_layer.group_send(f"stock_price_{price_data['symbol']}", {
            "type": "stock.price.update", # This corresponds to the method name in the consumer
            "data": price_data
        })

    # Handle Execution Report
    elif tr_id in ("H0STCNI0", "H0STCNI9"):
        try:
            decrypted_data = client.decrypt_websocket_data(parts[3])
            fields = decrypted_data.split('^')

            # Find the account this execution belongs to
            account_number = fields[0]
            account = await database_sync_to_async(TradingAccount.objects.filter(account_number__contains=account_number.replace('-', '')).first)()

            if not account:
                logger.warning(f"Received execution report for unknown account: {account_number}")
                return

            is_executed = fields[14] == '2'
            if is_executed:
                exec_data = {
                    'account_id': account.id,
                    'symbol': fields[3].strip(),
                    'order_id': fields[1],
                    'trade_type': 'BUY' if fields[10] == '02' else 'SELL',
                    'quantity': int(fields[7]),
                    'price': Decimal(fields[8]),
                    'timestamp': fields[19],
                }

                # Create the trade log asynchronously.
                # The post_save signal on TradeLog will handle broadcasting the update.
                await database_sync_to_async(TradeLog.objects.create)(
                    account=account,
                    symbol=exec_data['symbol'],
                    order_id=exec_data['order_id'],
                    trade_type=exec_data['trade_type'],
                    quantity=exec_data['quantity'],
                    price=exec_data['price'],
                    status='EXECUTED'
                )

        except Exception as e:
            logger.error(f"Error processing execution report from stream: {e}", exc_info=True)


@shared_task
def rebalance_portfolio_task():
    """
    Periodically re-analyzes all open positions in all active accounts
    and automatically updates their stop-loss and target prices based on the latest AI analysis.
    """
    logger.info("Celery Task: Starting periodic portfolio rebalancing.")

    active_accounts = TradingAccount.objects.filter(is_active=True)
    if not active_accounts.exists():
        logger.info("No active accounts to rebalance.")
        return

    # We can use the first account's client for all analysis calls
    first_account = active_accounts.first()
    client = KISApiClient(
        app_key=first_account.app_key,
        app_secret=first_account.app_secret,
        account_no=first_account.account_number,
        account_type=first_account.account_type
    )

    # Get the current market trend once to avoid re-calculating it for every stock
    market_trend = ai_analysis_service.get_market_trend(client)
    logger.info(f"Rebalancing with current market trend: {market_trend}")

    for account in active_accounts:
        open_positions = Portfolio.objects.filter(account=account, is_open=True)
        logger.info(f"Rebalancing {open_positions.count()} positions for account {account.account_name}.")

        for pos in open_positions:
            try:
                # Re-run the AI analysis for the stock
                analysis_result = ai_analysis_service.analyze_stock(pos.symbol, client, market_trend=market_trend)

                if analysis_result:
                    # Update the portfolio item with the new risk levels
                    pos.stop_loss_price = Decimal(analysis_result.stop_loss_price)
                    pos.target_price = Decimal(analysis_result.target_price)
                    pos.save()
                    logger.info(f"Updated risk levels for {pos.symbol}: SL={pos.stop_loss_price}, TP={pos.target_price}")
                else:
                    logger.warning(f"Could not re-analyze {pos.symbol} for rebalancing.")
            except Exception as e:
                logger.error(f"Error rebalancing position {pos.symbol} for account {account.id}: {e}", exc_info=True)

    logger.info("Celery Task: Periodic portfolio rebalancing finished.")