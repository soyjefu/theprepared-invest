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
    Celery task for the first stage of the trading process: initial stock screening.

    This task fetches top volume stocks from the KIS API, performs basic
    filtering, and saves the results to the AnalyzedStock model. It updates
    the cache with its progress for frontend display.
    """
    logger.info("Celery Task: Starting initial stock screening.")
    cache.set('screening_progress', {'status': 'Starting screening...', 'progress': 0}, timeout=300)
    try:
        screen_initial_stocks()
        cache.set('screening_progress', {'status': 'Screening complete', 'progress': 100}, timeout=60)
    except Exception as e:
        logger.error(f"An error occurred during stock screening: {e}", exc_info=True)
        cache.set('screening_progress', {'status': f'Error: {e}', 'progress': -1}, timeout=300)
    logger.info("Celery Task: Initial stock screening finished.")


@shared_task
def analyze_stocks_task():
    """
    Celery task for the second stage: AI-powered stock analysis.

    This task takes the stocks from the initial screening, performs a detailed
    AI analysis on each one to determine an investment horizon and risk management
    levels (stop-loss/target price), and updates the AnalyzedStock entries in the DB.
    """
    logger.info("Celery Task: Starting AI stock analysis.")
    cache.set('analysis_progress', {'status': 'Starting analysis...', 'progress': 0}, timeout=300)
    
    first_account = TradingAccount.objects.filter(is_active=True).first()
    if not first_account:
        logger.error("No active trading account found for API calls. Aborting analysis.")
        cache.set('analysis_progress', {'status': 'Error: No active account found', 'progress': -1}, timeout=300)
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
        cache.set('analysis_progress', {'status': 'Complete: No stocks to analyze', 'progress': 100}, timeout=60)
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
        status_text = f"Analyzing: {stock.stock_name} ({i + 1}/{total_stocks})"
        cache.set('analysis_progress', {'status': status_text, 'progress': progress}, timeout=300)

    logger.info("Celery Task: AI stock analysis finished.")
    cache.set('analysis_progress', {'status': 'Analysis complete', 'progress': 100}, timeout=60)


from decimal import Decimal
from .models import StrategySettings, Portfolio, TradeLog

@shared_task
def execute_ai_trades_task():
    """
    Celery task for the third stage: automated trade execution.

    Based on the AI analysis results, this task identifies new trading
    opportunities, calculates the appropriate trade size based on a
    pre-defined budget, and places buy orders via the KIS API.
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

    # 3. Get current portfolio from the database
    current_portfolio_symbols = list(Portfolio.objects.filter(account=account, is_open=True).values_list('symbol', flat=True))

    # 4. Identify new trading opportunities
    opportunities = AnalyzedStock.objects.filter(
        investment_horizon__in=['SHORT', 'MID', 'LONG']
    ).exclude(
        symbol__in=current_portfolio_symbols
    ).order_by('-analysis_date', '-last_price')

    if not opportunities:
        logger.info("No new trading opportunities found.")
        return

    logger.info(f"Found {len(opportunities)} new opportunities. Checking against portfolio balance.")

    # 5. Execute trades based on allocation strategy
    # This is a simplified logic that attempts to fill one new position if cash is available.
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

            order_response = client.place_order(
                account=account,
                symbol=opp.symbol,
                quantity=quantity_to_buy,
                price=int(stock_price),
                order_type='BUY'
            )

            # The creation of TradeLog and Portfolio is now handled by signals.
            # We just need to check if the order was accepted by the broker.
            if order_response and order_response.get('rt_cd') == '0':
                logger.info(f"AI trade order for {opp.symbol} was successfully sent to the broker.")
                # Reduce cash for next loop iteration to avoid over-ordering in the same run.
                cash_available -= (quantity_to_buy * stock_price)
            elif order_response and order_response.get('is_validation_error'):
                logger.warning(f"AI trade for {opp.symbol} failed validation: {order_response.get('msg1')}")
            else:
                logger.error(f"AI trade for {opp.symbol} failed at the broker: {order_response}")

    logger.info("Celery Task: AI trade execution finished.")


@shared_task
def run_all_active_strategies():
    """
    Placeholder task to prevent errors for a potentially deprecated task name.

    This task was likely part of a previous feature and may still be present in
    the scheduler's database. It does nothing to avoid breaking the system
    if a beat schedule tries to run it.
    """
    logger.info("Placeholder task 'run_all_active_strategies' executed. No action taken.")
    pass

@shared_task
def monitor_open_positions_task():
    """
    Celery task to monitor all open positions and execute sales if necessary.

    This task iterates through all open portfolio positions, fetches their
    current market price, and checks if the price has hit the pre-defined
    stop-loss or target-price levels. If a condition is met, it places a
    sell order.
    """
    logger.info("Celery Task: Starting real-time position monitoring.")

    account = TradingAccount.objects.filter(is_active=True).first()
    if not account:
        logger.warning("No active account for monitoring.")
        return

    open_positions = Portfolio.objects.filter(account=account, is_open=True)
    if not open_positions.exists():
        logger.info("No open positions to monitor.")
        return

    logger.info(f"Monitoring {open_positions.count()} open positions.")
    client = KISApiClient(app_key=account.app_key, app_secret=account.app_secret, account_no=account.account_number, account_type=account.account_type)

    for pos in open_positions:
        price_info_response = client.get_current_price(pos.symbol)
        if not (price_info_response and price_info_response.is_ok()):
            logger.warning(f"Could not fetch current price for {pos.symbol}. Skipping. "
                           f"Error: {price_info_response.get_error_message() if price_info_response else 'No response'}")
            continue

        price_info = price_info_response.get_body()
        current_price = Decimal(price_info.get('output', {}).get('stck_prpr', '0'))

        if current_price <= 0:
            continue

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
    A long-running Celery task to stream real-time data from the KIS WebSocket.

    This task establishes a persistent connection to the KIS WebSocket server.
    It uses a cache lock to ensure that only one instance of the streamer
    is running across all Celery workers. The task handles reconnection logic
    and delegates message processing to async helper functions.
    """
    logger.info("Attempting to start KIS WebSocket data streamer task.")

    if not cache.add("kis_streamer_lock", "running", timeout=None):
        logger.warning("KIS data streamer task is already running. Exiting.")
        return

    try:
        async_to_sync(run_streamer)()
    except Exception as e:
        logger.error(f"KIS data streamer task failed: {e}", exc_info=True)
    finally:
        cache.delete("kis_streamer_lock")
        logger.info("KIS data streamer task stopped and lock released.")


async def run_streamer():
    """
    The core async function that manages the WebSocket connection and subscriptions.

    It connects to the KIS server, subscribes to execution reports for all active
    accounts and price updates for all stocks in the portfolio, and then enters
    an infinite loop to listen for messages.
    """
    channel_layer = get_channel_layer()

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

                all_accounts = await database_sync_to_async(list)(TradingAccount.objects.filter(is_active=True))
                for account in all_accounts:
                    await subscribe_to_executions(websocket, approval_key, account, client.is_simulation)

                all_symbols = await database_sync_to_async(list)(
                    Portfolio.objects.filter(is_open=True).values_list('symbol', flat=True).distinct()
                )
                for symbol in all_symbols:
                    await subscribe_to_price(websocket, approval_key, symbol)

                async for message in websocket:
                    await handle_stream_message(message, channel_layer, client)

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"KIS streamer connection closed: {e}. Reconnecting in 5 seconds...")
        except Exception as e:
            logger.error(f"Error in KIS streamer: {e}. Reconnecting in 5 seconds...", exc_info=True)

        await asyncio.sleep(5)


async def subscribe_to_executions(websocket, key, account, is_sim):
    """
    Sends a WebSocket message to subscribe to trade execution reports.

    Args:
        websocket: The WebSocket connection object.
        key (str): The WebSocket approval key.
        account (TradingAccount): The account to subscribe for.
        is_sim (bool): True if the account is for simulation.
    """
    tr_id = "H0STCNI9" if is_sim else "H0STCNI0"
    user_id = account.user.username
    subscription_data = {
        "header": {"approval_key": key, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
        "body": {"input": {"tr_id": tr_id, "tr_key": user_id}}
    }
    await websocket.send(json.dumps(subscription_data))
    logger.info(f"Subscribed to execution reports for account {account.account_number}")

async def subscribe_to_price(websocket, key, symbol):
    """
    Sends a WebSocket message to subscribe to real-time price updates for a stock.

    Args:
        websocket: The WebSocket connection object.
        key (str): The WebSocket approval key.
        symbol (str): The stock symbol to subscribe to.
    """
    subscription_data = {
        "header": {"approval_key": key, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
        "body": {"input": {"tr_id": "JEQ", "tr_key": symbol}}
    }
    await websocket.send(json.dumps(subscription_data))
    logger.info(f"Subscribed to price updates for symbol {symbol}")


async def handle_stream_message(message, channel_layer, client):
    """
    Parses and handles incoming messages from the KIS WebSocket stream.

    It identifies message types (price update vs. execution report), decrypts
    data where necessary, and broadcasts the processed data to the relevant
    Django Channels group for real-time frontend updates.

    Args:
        message (str): The raw message from the WebSocket.
        channel_layer: The Django Channels layer for broadcasting.
        client (KISApiClient): The API client, needed for decryption.
    """
    if message.startswith('{'):
        logger.info(f"KIS stream received JSON message: {message}")
        return

    parts = message.split('|')
    if len(parts) < 2:
        logger.warning(f"Unknown message format from KIS stream: {message}")
        return

    tr_id = parts[1]

    if tr_id == "JEQ": # Real-time price update
        price_data = {
            'type': 'stock_price_update',
            'symbol': parts[2].strip(),
            'price': abs(int(parts[3])),
            'volume': int(parts[12]),
        }
        await channel_layer.group_send(f"stock_price_{price_data['symbol']}", {
            "type": "stock.price.update",
            "data": price_data
        })

    elif tr_id in ("H0STCNI0", "H0STCNI9"): # Execution report
        try:
            decrypted_data = client.decrypt_websocket_data(parts[3])
            fields = decrypted_data.split('^')

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

                # Create the trade log asynchronously. The post_save signal on
                # TradeLog will handle broadcasting the update to the frontend.
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
    Celery task to periodically rebalance the portfolio.

    This task re-analyzes all open positions in active accounts and updates
    their stop-loss and target prices based on the latest AI analysis. This
    allows the risk management strategy to adapt to changing market conditions.
    """
    logger.info("Celery Task: Starting periodic portfolio rebalancing.")

    active_accounts = TradingAccount.objects.filter(is_active=True)
    if not active_accounts.exists():
        logger.info("No active accounts to rebalance.")
        return

    first_account = active_accounts.first()
    client = KISApiClient(
        app_key=first_account.app_key,
        app_secret=first_account.app_secret,
        account_no=first_account.account_number,
        account_type=first_account.account_type
    )

    market_trend = ai_analysis_service.get_market_trend(client)
    logger.info(f"Rebalancing with current market trend: {market_trend}")

    for account in active_accounts:
        open_positions = Portfolio.objects.filter(account=account, is_open=True)
        logger.info(f"Rebalancing {open_positions.count()} positions for account {account.account_name}.")

        for pos in open_positions:
            try:
                analysis_result = ai_analysis_service.analyze_stock(pos.symbol, client, market_trend=market_trend)

                if analysis_result:
                    pos.stop_loss_price = Decimal(analysis_result.stop_loss_price)
                    pos.target_price = Decimal(analysis_result.target_price)
                    pos.save()
                    logger.info(f"Updated risk levels for {pos.symbol}: SL={pos.stop_loss_price}, TP={pos.target_price}")
                else:
                    logger.warning(f"Could not re-analyze {pos.symbol} for rebalancing.")
            except Exception as e:
                logger.error(f"Error rebalancing position {pos.symbol} for account {account.id}: {e}", exc_info=True)

    logger.info("Celery Task: Periodic portfolio rebalancing finished.")