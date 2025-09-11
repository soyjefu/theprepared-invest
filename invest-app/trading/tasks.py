# invest-app/trading/tasks.py

from celery import shared_task
import logging
from .models import AccountStrategy, AnalyzedStock
from .strategy_handler import run_strategy
from .analysis.market_scanner import screen_initial_stocks

logger = logging.getLogger(__name__)

# --- 수정: 새로운 스크리너 작업 추가 ---
@shared_task
def screen_stocks_task():
    """
    1차 종목 스크리닝을 실행하는 Celery 작업.
    """
    logger.info("Celery 작업: 1차 종목 스크리닝 시작")
    screen_initial_stocks()

@shared_task
def execute_strategy_task(account_strategy_id, symbol):
    logger.info(f"Celery 작업 시작: account_strategy_id={account_strategy_id}, symbol={symbol}")
    run_strategy(account_strategy_id, symbol)

@shared_task
def run_all_active_strategies():
    logger.info("모든 활성 전략 실행을 시작합니다...")
    
    # 수정: 이제 DB에 저장된 1차 분석 통과 종목을 대상으로 전략 실행
    target_symbols = list(AnalyzedStock.objects.filter(is_investable=True).values_list('symbol', flat=True))
    
    if not target_symbols:
        logger.info("분석할 대상 종목이 없습니다. 먼저 종목 스크리너를 실행해야 합니다.")
        return
        
    logger.info(f"오늘의 분석 대상 종목 ({len(target_symbols)}개)를 DB에서 가져왔습니다.")

    active_account_strategies = AccountStrategy.objects.filter(is_active=True, account__is_active=True, strategy__is_active=True)
    
    if not active_account_strategies:
        logger.info("실행할 활성 전략이 없습니다.")
        return

    for acc_strategy in active_account_strategies:
        for symbol in target_symbols:
            execute_strategy_task.delay(acc_strategy.id, symbol)

    logger.info(f"{len(active_account_strategies) * len(target_symbols)}개의 전략 실행 작업이 예약되었습니다.")