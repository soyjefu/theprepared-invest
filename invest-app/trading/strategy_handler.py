# invest-app/trading/strategy_handler.py

import logging
from .models import AccountStrategy
from .kis_client import KISApiClient
from .strategies.golden_cross import GoldenCrossStrategy
from .strategies.ai_strategy import AIStrategy # 수정: AIStrategy import
from .risk_management import RiskManager

logger = logging.getLogger(__name__)

# 수정: STRATEGY_MAP에 ai_strategy 추가
STRATEGY_MAP = {
    'golden_cross': GoldenCrossStrategy,
    'ai_strategy': AIStrategy, 
}

# run_strategy 함수는 이전과 동일
def run_strategy(account_strategy_id, symbol, force_run=False):
    try:
        acc_strategy = AccountStrategy.objects.select_related('account', 'strategy').get(id=account_strategy_id)
        account = acc_strategy.account
        strategy_model = acc_strategy.strategy
        
        client = KISApiClient(
            app_key=account.app_key, app_secret=account.app_secret,
            account_no=account.account_number, account_type=account.account_type
        )
        
        if not force_run and not client.is_market_open():
            logger.info(f"장이 열리지 않아 '{strategy_model.name}' 전략 실행을 건너뜁니다.")
            return
        
        risk_manager = RiskManager(client, account)
        if not risk_manager.assess(symbol, 'BUY'): # 현재는 'BUY'만 가정
            logger.info(f"[{symbol}] 리스크 관리 규칙에 따라 거래를 실행하지 않습니다.")
            return
        
        logger.info(f"전략 분석 시작: 계좌='{account.account_name}', 전략='{strategy_model.name}', 종목='{symbol}'")

        StrategyClass = STRATEGY_MAP.get(strategy_model.name)
        if not StrategyClass:
            logger.error(f"'{strategy_model.name}'에 해당하는 전략 클래스를 찾을 수 없습니다.")
            return

        strategy_instance = StrategyClass(client, account, strategy_model, symbol)
        strategy_instance.run()

        logger.info(f"전략 실행 완료: 계좌='{account.account_name}', 전략='{strategy_model.name}', 종목='{symbol}'")

    except AccountStrategy.DoesNotExist:
        logger.error(f"ID가 '{account_strategy_id}'인 AccountStrategy를 찾을 수 없습니다.")
    except Exception as e:
        logger.error(f"전략 실행 중 예외 발생: {e}", exc_info=True)