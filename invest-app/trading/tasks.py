# invest-app/trading/tasks.py

from celery import shared_task
from .analysis import screen_investable_stocks, classify_investment_horizon, establish_trading_strategies
# from .strategy_handler import run_all_active_strategies # 기존 매매 실행 로직

@shared_task
def run_daily_morning_routine():
    """
    매일 아침 장 시작 전에 실행되는 전체 자동화 워크플로우입니다.
    1. 1차 분석: 투자가치 있는 종목 스크리닝
    2. 2차 분석: 투자 기간(단기/중기/장기) 분류
    3. 3차 분석: 포트폴리오 리밸런싱 및 신규 매매 전략 수립
    """
    print("===== [Celery Task] 매일 아침 자동 분석 및 매매 준비 시작 =====")
    
    # 1차 분석 실행
    screen_investable_stocks()
    
    # 2차 분석 실행
    classify_investment_horizon()
    
    # 3차 분석 실행 (매일 아침에는 모든 포지션 점검 및 단기 투자 전략 수립)
    establish_trading_strategies()
    
    print("===== [Celery Task] 매일 아침 자동 분석 및 매매 준비 완료 =====")
    
    # 4. 실제 매매 실행 (기존 로직 호출)
    # print("===== [Celery Task] 모든 활성 전략 실행 시작 =====")
    # run_all_active_strategies()
    # print("===== [Celery Task] 모든 활성 전략 실행 완료 =====")


@shared_task
def run_periodic_rebalancing(horizon):
    """
    주기적(월간/분기별)으로 중장기 투자 종목에 대한 심층 분석 및 리밸런싱을 수행합니다.
    (현재는 일일 분석 로직에 통합되어 있으나, 추후 더 복잡한 분석을 위해 분리 가능)
    """
    print(f"===== [Celery Task] {horizon} 투자 주기 리밸런싱 시작 =====")
    # TODO: 중기/장기 투자에 특화된 별도의 심층 분석 및 리밸런싱 로직 구현
    # 예: establish_trading_strategies(horizon='MID') 와 같이 파라미터를 넘겨 분기 처리
    print(f"===== [Celery Task] {horizon} 투자 주기 리밸런싱 완료 =====")