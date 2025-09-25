import pandas as pd
import logging

logger = logging.getLogger(__name__)

def calculate_atr(daily_price_history: list, period: int = 14) -> float:
    """
    일봉 데이터 리스트를 기반으로 ATR(Average True Range)을 계산합니다.

    Args:
        daily_price_history (list): KIS API의 'inquire-daily-itemchartprice' 결과의
                                   output2 리스트. 각 항목은 dict 형태여야 합니다.
                                   (필수 키: 'stck_hgpr', 'stck_lwpr', 'stck_clpr')
        period (int): ATR 계산에 사용할 기간. 기본값은 14일입니다.

    Returns:
        float: 계산된 최신 ATR 값. 계산이 불가능하면 0.0을 반환합니다.
    """
    if not daily_price_history or len(daily_price_history) < period:
        logger.warning(f"ATR 계산을 위한 데이터 부족. 데이터 개수: {len(daily_price_history)}, 필요 기간: {period}")
        return 0.0

    try:
        # KIS API 응답(string)을 float으로 변환하여 DataFrame 생성
        df = pd.DataFrame(daily_price_history)
        df['high'] = df['stck_hgpr'].astype(float)
        df['low'] = df['stck_lwpr'].astype(float)
        df['close'] = df['stck_clpr'].astype(float)

        # True Range(TR) 계산
        df['tr1'] = abs(df['high'] - df['low'])
        df['tr2'] = abs(df['high'] - df['close'].shift(1))
        df['tr3'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)

        # ATR 계산 (Exponential Moving Average 사용)
        df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()

        # 최신 ATR 값 반환
        latest_atr = df['atr'].iloc[-1]
        return float(latest_atr)

    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"ATR 계산 중 오류 발생: {e}", exc_info=True)
        return 0.0

def get_price_targets(atr: float, buy_price: float, current_price: float, group: str):
    """
    종목 그룹('일반' 또는 '중/장기')에 따라 목표가와 손절가를 계산합니다.

    Args:
        atr (float): 계산된 ATR 값.
        buy_price (float): 매수 가격.
        current_price (float): 현재 가격 (샹들리에 청산에 사용).
        group (str): 종목 그룹. '일반' 또는 '중/장기'.

    Returns:
        dict: {'target_price': float, 'stop_loss_price': float}
              목표가가 없는 경우(예: 트레일링 스탑) target_price는 None일 수 있습니다.
    """
    if atr <= 0 or buy_price <= 0:
        return {'target_price': None, 'stop_loss_price': None}

    if group == '일반':
        target_price = buy_price + (4 * atr)
        stop_loss_price = buy_price - (2 * atr)
        return {
            'target_price': target_price,
            'stop_loss_price': stop_loss_price
        }

    elif group == '중/장기':
        # 초기 손절가는 매수가 기준
        initial_stop_loss = buy_price - (3 * atr)

        # Chandelier Exit (샹들리에 청산) 가격 계산
        chandelier_exit = current_price - (3 * atr)

        # 트레일링 스탑: 둘 중 더 높은 가격을 손절가로 사용
        # (주가가 상승함에 따라 손절 라인도 함께 올라감)
        stop_loss_price = max(initial_stop_loss, chandelier_exit)

        return {
            'target_price': None,  # 고정 목표가 없음
            'stop_loss_price': stop_loss_price,
            'trailing_stop': chandelier_exit # 참고용으로 추가
        }

    else:
        return {'target_price': None, 'stop_loss_price': None}