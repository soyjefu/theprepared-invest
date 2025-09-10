# invest-app/trading/strategies/golden_cross.py

import logging
from .strategy_base import StrategyBase
from trading.models import TradeLog

logger = logging.getLogger(__name__)

class GoldenCrossStrategy(StrategyBase):
    """
    골든크로스 매매 전략.
    단기 이동평균선이 장기 이동평균선을 상향 돌파할 때 매수 신호를 생성하고 주문을 실행합니다.
    """
    def run(self):
        short_ma_period = self.params.get('short_ma', 5)
        long_ma_period = self.params.get('long_ma', 20)
        logger.info(f"[{self.symbol}] 골든크로스 전략 분석 시작. 단기MA:{short_ma_period}, 장기MA:{long_ma_period}")

        price_df = self._get_price_history_df(days=long_ma_period + 50) 
        if price_df is None or len(price_df) < long_ma_period:
            logger.warning(f"[{self.symbol}] 분석을 위한 충분한 데이터를 가져오지 못했습니다.")
            return

        price_df[f'short_ma'] = price_df['stck_clpr'].rolling(window=short_ma_period).mean()
        price_df[f'long_ma'] = price_df['stck_clpr'].rolling(window=long_ma_period).mean()

        latest = price_df.iloc[-1]
        previous = price_df.iloc[-2]

        if latest['short_ma'] > latest['long_ma'] and previous['short_ma'] < previous['long_ma']:
            logger.info(f"✅ [{self.symbol}] 골든크로스 발생! 매수 신호를 포착했습니다.")
            
            quantity_to_order = 1
            order_price = int(latest['stck_clpr'])
            logger.info(f"[{self.symbol}] 자동 매수 주문을 시도합니다. 수량: {quantity_to_order}, 가격: {order_price}")

            order_response = self.client.place_order(
                symbol=self.symbol, quantity=quantity_to_order,
                price=order_price, order_type='BUY'
            )

            if order_response and order_response.get('rt_cd') == '0':
                order_id = order_response.get('output', {}).get('ODNO', 'N/A')
                status = TradeLog.TradeStatus.EXECUTED
                message = f"주문 성공: {order_response.get('msg1', '')}"
                logger.info(f"✅ [{self.symbol}] 주문이 성공적으로 접수되었습니다. 주문번호: {order_id}")
            else:
                order_id = "FAILED"
                status = TradeLog.TradeStatus.FAILED
                message = order_response.get('msg1', '알 수 없는 오류') if order_response else "API 응답 없음"
                logger.error(f"🚨 [{self.symbol}] 주문 접수 실패: {message}")
            
            TradeLog.objects.create(
                account=self.account, strategy=self.strategy_model, symbol=self.symbol,
                order_id=order_id, trade_type=TradeLog.TradeType.BUY,
                quantity=quantity_to_order, price=order_price,
                status=status, log_message=message
            )
            logger.info(f"[{self.symbol}] 거래 결과가 TradeLog에 기록되었습니다.")
        else:
            logger.info(f"[{self.symbol}] 매수 신호가 없습니다. 현재 단기MA: {latest['short_ma']:.2f}, 장기MA: {latest['long_ma']:.2f}")