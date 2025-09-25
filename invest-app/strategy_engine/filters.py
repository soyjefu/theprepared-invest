import logging
from decimal import Decimal
import pandas as pd

logger = logging.getLogger(__name__)

# 금융업 등 특정 업종은 부채비율 기준에서 제외하기 위한 목록
FINANCE_SECTOR_CODES = ['64', '65', '66']  # 예: 은행 및 저축기관, 보험, 증권 등 (KRX 업종 분류 기준)

def is_financially_sound(stock_details, financial_data):
    """
    '일반' 종목 선정을 위한 기본 재무/시장 건전성을 검사합니다.

    - 거래대금 20일 평균 50억 이상
    - 시가총액 1,000억 이상
    - 부채비율 200% 미만 (금융업 제외)
    - 이자보상배율 3배 이상
    - ROE 5% 이상
    - 최근 3년 중 2년 이상 영업이익 흑자
    - 관리종목, 투자경고/위험, 자본잠식 등 제외
    """
    try:
        # 시장 조건
        if stock_details.get('avg_20d_turnover', 0) < 5_000_000_000:
            return False, "거래대금 미달"
        if stock_details.get('market_cap', 0) < 100_000_000_000:
            return False, "시가총액 미달"

        # 제외 조건
        if stock_details.get('is_admin_issue', False) or \
           stock_details.get('is_investment_alert', False) or \
           stock_details.get('is_capital_impaired', False):
            return False, "관리/경고 종목 또는 자본잠식"

        # 재무 건전성 (최신 재무 데이터 기준)
        latest_financials = financial_data[0] if financial_data else {}

        # 부채비율 (금융업 제외)
        if stock_details.get('sector_code') not in FINANCE_SECTOR_CODES:
            debt_ratio = Decimal(latest_financials.get('debt_ratio', '9999'))
            if debt_ratio >= 200:
                return False, f"부채비율 초과 ({debt_ratio}%)"

        # 이자보상배율
        interest_coverage_ratio = Decimal(latest_financials.get('interest_coverage_ratio', '0'))
        if interest_coverage_ratio < 3:
            return False, f"이자보상배율 미달 ({interest_coverage_ratio})"

        # 수익성
        roe = Decimal(latest_financials.get('roe', '0'))
        if roe < 5:
            return False, f"ROE 미달 ({roe}%)"

        # 영업이익 흑자 (최근 3개년 데이터 확인)
        op_profit_positive_years = 0
        for data in financial_data[:3]:
            if Decimal(data.get('operating_profit', '0')) > 0:
                op_profit_positive_years += 1
        if op_profit_positive_years < 2:
            return False, "영업이익 흑자 조건 미달"

        return True, "통과"

    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"재무 건전성 평가 중 오류 발생: {e}")
        return False, "데이터 오류"


def is_blue_chip(stock_details, financial_data):
    """
    '중/장기' 태그 부여를 위한 우량주 조건을 검사합니다.

    - 부채비율 100% 미만
    - 유동비율 150% 이상
    - ROE 3년 평균 12% 이상
    - 영업이익률 3년 평균 10% 이상
    - 매출액 성장률 3년 연평균 5% 이상
    - EPS 성장률 3년 연평균 5% 이상
    - 3년 연속 배당 실시
    """
    try:
        if len(financial_data) < 3:
            return False, "3년치 재무 데이터 부족"

        # 안정성
        if Decimal(financial_data[0].get('debt_ratio', '9999')) >= 100:
            return False, "부채비율 100% 이상"
        if Decimal(financial_data[0].get('current_ratio', '0')) < 150:
            return False, "유동비율 150% 미만"

        # 수익성 (3년 평균)
        avg_roe = sum(Decimal(d.get('roe', '0')) for d in financial_data[:3]) / 3
        if avg_roe < 12:
            return False, f"3년 평균 ROE 미달 ({avg_roe:.2f}%)"

        avg_op_margin = sum(Decimal(d.get('operating_margin', '0')) for d in financial_data[:3]) / 3
        if avg_op_margin < 10:
            return False, f"3년 평균 영업이익률 미달 ({avg_op_margin:.2f}%)"

        # 성장성 (3년 연평균)
        sales_gpr = Decimal(financial_data[0].get('sales_growth_yoy', '0'))
        eps_gpr = Decimal(financial_data[0].get('eps_growth_yoy', '0'))
        # KIS API가 연평균 성장률(CAGR)을 직접 제공하지 않으므로, 여기서는 전년 대비 성장률(YoY)을 기준으로 근사치를 사용합니다.
        # 정확한 CAGR 계산을 위해서는 3년 전 데이터가 필요하며, 로직 보강이 필요할 수 있습니다.
        if sales_gpr < 5:
            return False, f"매출액 성장률 미달 ({sales_gpr:.2f}%)"
        if eps_gpr < 5:
            return False, f"EPS 성장률 미달 ({eps_gpr:.2f}%)"

        # 주주환원
        has_dividend_3yrs = all(Decimal(d.get('dividend_per_share', '0')) > 0 for d in financial_data[:3])
        if not has_dividend_3yrs:
            return False, "3년 연속 배당 미실시"

        return True, "통과"

    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"우량주 평가 중 오류 발생: {e}")
        return False, "데이터 오류"


def determine_market_mode(kospi_history: list):
    """
    코스피 지수와 60일 이동평균을 비교하여 시장 모드를 결정합니다.

    Args:
        kospi_history (list): KIS API의 코스피 일봉 데이터 리스트.

    Returns:
        str: '단기 트레이딩 모드' 또는 '우량주 분할매수 모드'.
             계산이 불가능할 경우 '단기 트레이딩 모드'(기본값)를 반환합니다.
    """
    if not kospi_history or len(kospi_history) < 60:
        logger.warning("시장 모드 결정을 위한 데이터 부족. 기본 모드로 진행.")
        return '단기 트레이딩 모드' # 기본값

    try:
        df = pd.DataFrame(kospi_history)
        df['close'] = pd.to_numeric(df['stck_clpr'])

        # 60일 이동평균 계산
        df['ma_60'] = df['close'].rolling(window=60).mean()

        latest_close = df['close'].iloc[-1]
        latest_ma_60 = df['ma_60'].iloc[-1]

        if latest_close > latest_ma_60:
            return '단기 트레이딩 모드'
        else:
            return '우량주 분할매수 모드'

    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"시장 모드 결정 중 오류 발생: {e}", exc_info=True)
        return '단기 트레이딩 모드' # 오류 발생 시 기본값