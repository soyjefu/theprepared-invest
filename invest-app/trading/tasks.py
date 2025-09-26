import logging
from celery import shared_task
from django.contrib.auth.models import User

from strategy_engine.services import UniverseScreener
from .trading_service import DailyTrader
from .models import TradingAccount

logger = logging.getLogger(__name__)


@shared_task
def run_stock_screening_task():
    """
    Celery task to run the universe screening process.
    This should be run weekly as per the requirements.
    """
    logger.info("Celery 작업: 주간 유니버스 스크리닝을 시작합니다.")
    try:
        # 시스템에서 활성화된 첫 번째 트레이딩 계정을 찾아 스크리닝을 실행합니다.
        # 스크리닝 프로세스는 활성 계정을 가진 어떤 사용자에 의해서도 수행될 수 있다고 가정합니다.
        active_account = TradingAccount.objects.filter(is_active=True).first()
        if not active_account:
            logger.error("활성화된 트레이딩 계좌가 없습니다. 스크리너를 실행할 수 없습니다.")
            return

        # 해당 계정의 사용자를 가져옵니다.
        user = active_account.user
        screener = UniverseScreener(user=user)
        screener.screen_all_stocks()
        logger.info("Celery 작업: 주간 유니버스 스크리닝이 성공적으로 완료되었습니다.")

    except Exception as e:
        logger.error(f"주간 주식 스크리닝 작업 중 오류 발생: {e}", exc_info=True)


@shared_task
def run_daily_trader_task():
    """
    Celery task to run the main daily trading logic for all active accounts.
    This task determines the market mode, manages open positions (sells),
    and executes new buys based on the defined strategies.
    """
    logger.info("Celery Task: Starting daily trading logic execution.")

    active_accounts = TradingAccount.objects.filter(is_active=True)
    if not active_accounts.exists():
        logger.warning("No active trading accounts found. Skipping daily trading.")
        return

    for account in active_accounts:
        try:
            logger.info(f"Running daily trader for account: {account.account_number}")
            trader = DailyTrader(user=account.user, account_number=account.account_number)
            trader.run_daily_trading()
        except Exception as e:
            logger.error(f"An error occurred while running daily trader for account {account.account_number}: {e}", exc_info=True)

    logger.info("Celery Task: Daily trading logic execution finished for all active accounts.")


# --- Deprecated Task Placeholders ---
# The following tasks are kept as placeholders to prevent Celery Beat from
# crashing if old schedules are still present in the database.
# They should be removed once the Celery Beat schedule is confirmed to be clean.