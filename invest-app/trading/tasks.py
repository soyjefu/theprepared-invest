# invest-app/trading/tasks.py

from celery import shared_task
import logging
from .models import AccountStrategy
from .strategy_handler import run_strategy

logger = logging.getLogger(__name__)

@shared_task
def execute_strategy_task(account_strategy_id, symbol):
    """
    지정된 계좌-전략 연결 정보를 바탕으로 단일 전략을 실행하는 작업.
    """
    logger.info(f"Celery 작업 시작: account_strategy_id={account_strategy_id}, symbol={symbol}")
    run_strategy(account_strategy_id, symbol)

@shared_task
def run_all_active_strategies():
    """
    DB에서 활성화된 모든 '계좌-전략' 설정을 찾아 각각에 대한 작업을 실행시키는 스케줄러용 작업.
    """
    logger.info("모든 활성 전략 실행을 시작합니다...")
    active_strategies = AccountStrategy.objects.filter(is_active=True, account__is_active=True, strategy__is_active=True)
    
    if not active_strategies:
        logger.info("실행할 활성 전략이 없습니다.")
        return

    for acc_strategy in active_strategies:
        # TODO: 현재는 모든 전략이 삼성전자(005930)에 대해서만 실행됨.
        # 향후에는 각 전략이 감시할 종목 목록을 DB에서 가져오도록 확장해야 함.
        symbol_to_trade = "005930" 
        execute_strategy_task.delay(acc_strategy.id, symbol_to_trade)

    logger.info(f"{len(active_strategies)}개의 활성 전략에 대한 작업이 예약되었습니다.")