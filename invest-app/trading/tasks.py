import logging
from celery import shared_task
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
    
    # API 호출을 위한 기본 계정 설정
    first_account = TradingAccount.objects.filter(is_active=True).first()
    if not first_account:
        logger.error("No active trading account found for API calls. Aborting analysis.")
        return

    client = KISApiClient(
        app_key=first_account.app_key,
        app_secret=first_account.app_secret,
        account_no=first_account.account_number,
        account_type=first_account.account_type
    )

    # 분석 대상 종목 조회
    stocks_to_analyze = AnalyzedStock.objects.filter(is_investable=True)
    logger.info(f"Found {stocks_to_analyze.count()} stocks to analyze.")

    for stock in stocks_to_analyze:
        try:
            analysis_result = analyze_stock(stock.symbol, client)
            if analysis_result:
                stock.investment_horizon = analysis_result.horizon
                # raw_analysis_data에 분석 결과의 핵심 지표들을 저장
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

    logger.info("Celery Task: AI stock analysis finished.")


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

            # Place order
            order_response = client.place_order(symbol=opp.symbol, quantity=quantity_to_buy, price=int(stock_price), order_type='BUY')

            if order_response and order_response.get('rt_cd') == '0':
                order_id = order_response.get('output', {}).get('ODNO', 'N/A')
                logger.info(f"Successfully placed buy order for {opp.symbol}. Order ID: {order_id}")

                # Create TradeLog
                trade_log = TradeLog.objects.create(
                    account=account,
                    symbol=opp.symbol,
                    order_id=order_id,
                    trade_type='BUY',
                    quantity=quantity_to_buy,
                    price=stock_price,
                    status='EXECUTED' # Assuming immediate execution for simplicity
                )

                # Create Portfolio entry
                Portfolio.objects.create(
                    account=account,
                    symbol=opp.symbol,
                    stock_name=opp.stock_name,
                    quantity=quantity_to_buy,
                    average_buy_price=stock_price,
                    stop_loss_price=opp.raw_analysis_data.get('stop_loss_price', stock_price * Decimal('0.9')),
                    target_price=opp.raw_analysis_data.get('target_price', stock_price * Decimal('1.2')),
                    is_open=True,
                    entry_log=trade_log
                )

                # Reduce cash for next loop iteration
                cash_available -= (quantity_to_buy * stock_price)

            else:
                logger.error(f"Failed to place order for {opp.symbol}: {order_response}")
                TradeLog.objects.create(
                    account=account,
                    symbol=opp.symbol,
                    order_id='N/A',
                    trade_type='BUY',
                    quantity=quantity_to_buy,
                    price=stock_price,
                    status='FAILED',
                    log_message=str(order_response)
                )

    logger.info("Celery Task: AI trade execution finished.")


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

            # Place sell order
            order_response = client.place_order(symbol=pos.symbol, quantity=pos.quantity, price=int(current_price), order_type='SELL')

            if order_response and order_response.get('rt_cd') == '0':
                order_id = order_response.get('output', {}).get('ODNO', 'N/A')
                logger.info(f"Successfully placed SELL order for {pos.symbol}. Order ID: {order_id}")

                # Create TradeLog
                TradeLog.objects.create(
                    account=account,
                    symbol=pos.symbol,
                    order_id=order_id,
                    trade_type='SELL',
                    quantity=pos.quantity,
                    price=current_price,
                    status='EXECUTED',
                    log_message=sell_reason
                )

                # Close position in portfolio
                pos.is_open = False
                pos.save()

            else:
                logger.error(f"Failed to place SELL order for {pos.symbol}: {order_response}")
                TradeLog.objects.create(
                    account=account,
                    symbol=pos.symbol,
                    order_id='N/A',
                    trade_type='SELL',
                    quantity=pos.quantity,
                    price=current_price,
                    status='FAILED',
                    log_message=f"Reason: {sell_reason}. Error: {order_response}"
                )

    logger.info("Celery Task: Real-time position monitoring finished.")