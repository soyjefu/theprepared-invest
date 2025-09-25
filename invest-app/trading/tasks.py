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
    logger.info("Celery Task: Starting weekly universe screening.")
    try:
        # This task should ideally be run for a specific system user or
        # for each active user account depending on the multi-tenancy design.
        # Here, we assume a single-user context or a system-wide screening.
        user = User.objects.first()
        if not user:
            logger.error("No users found in the system. Cannot run screener.")
            return

        screener = UniverseScreener(user=user)
        screener.screen_all_stocks()
        logger.info("Celery Task: Weekly universe screening finished successfully.")

    except Exception as e:
        logger.error(f"An error occurred during the weekly stock screening task: {e}", exc_info=True)


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

@shared_task
def run_daily_morning_routine():
    logger.warning("Deprecated task 'run_daily_morning_routine' was called. Please use 'run_stock_screening_task' instead.")

@shared_task
def analyze_stocks_task():
    logger.warning("Deprecated task 'analyze_stocks_task' was called. This logic is now part of the screening and trading services.")

@shared_task
def execute_ai_trades_task():
    logger.warning("Deprecated task 'execute_ai_trades_task' was called. Please use 'run_daily_trader_task' instead.")

@shared_task
def monitor_open_positions_task():
    logger.warning("Deprecated task 'monitor_open_positions_task' was called. This logic is now part of the DailyTrader service.")