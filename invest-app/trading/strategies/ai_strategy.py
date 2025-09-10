# invest-app/trading/strategies/ai_strategy.py

import logging
from .strategy_base import StrategyBase
from trading.ai_model_handler import get_ai_prediction # 가상 AI 모델 핸들러 import
from trading.models import TradeLog

logger = logging.getLogger(__name__)

class AIStrategy(StrategyBase):
    """
    AI 모델의 예측을 기반으로 매매 신호를 생성하는 전략.
    """
    def run(self):
        logger.info(f"[{self.symbol}] AI 기반 전략 분석을 시작합니다.")
        
        # 1. AI 모델로부터 매매 신호를 받습니다.
        signal = get_ai_prediction(self.symbol)
        
        # 2. 신호에 따라 주문을 실행합니다.
        if signal == 'BUY':
            logger.info(f"✅ [{self.symbol}] AI 모델이 '매수' 신호를 생성했습니다.")
            
            # 현재가로 1주 매수 주문 (예시)
            price_info = self.client.get_current_price(self.symbol)
            if not (price_info and price_info.get('rt_cd') == '0'):
                logger.error(f"[{self.symbol}] 주문을 위한 현재가 조회에 실패했습니다.")
                return

            quantity_to_order = 1
            order_price = int(price_info.get('output', {}).get('stck_prpr', '0'))
            
            logger.info(f"[{self.symbol}] 자동 매수 주문을 시도합니다. 수량: {quantity_to_order}, 가격: {order_price}")

            order_response = self.client.place_order(
                symbol=self.symbol, quantity=quantity_to_order,
                price=order_price, order_type='BUY'
            )

            # ... (주문 결과 로그 기록 로직은 golden_cross.py와 동일) ...
            if order_response and order_response.get('rt_cd') == '0':
                order_id = order_response.get('output', {}).get('ODNO', 'N/A')
                status = TradeLog.TradeStatus.EXECUTED
                message = f"AI 전략 주문 성공: {order_response.get('msg1', '')}"
                logger.info(f"✅ [{self.symbol}] 주문이 성공적으로 접수되었습니다. 주문번호: {order_id}")
            else:
                order_id = "FAILED"
                status = TradeLog.TradeStatus.FAILED
                message = order_response.get('msg1', 'AI 전략 주문 실패') if order_response else "API 응답 없음"
                logger.error(f"🚨 [{self.symbol}] 주문 접수 실패: {message}")
            
            TradeLog.objects.create(
                account=self.account, strategy=self.strategy_model, symbol=self.symbol,
                order_id=order_id, trade_type=TradeLog.TradeType.BUY,
                quantity=quantity_to_order, price=order_price,
                status=status, log_message=message
            )
        
        elif signal == 'SELL':
            logger.info(f"[{self.symbol}] AI 모델이 '매도' 신호를 생성했습니다. (매도 로직은 구현되지 않음)")
            # TODO: 향후 매도 로직 구현
        
        else: # HOLD
            logger.info(f"[{self.symbol}] AI 모델이 '보유' 신호를 생성했습니다.")