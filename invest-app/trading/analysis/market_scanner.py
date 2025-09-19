# invest-app/trading/analysis/market_scanner.py

import logging
import numpy as np
from django.core.cache import cache
from trading.models import AnalyzedStock, TradingAccount
from trading.kis_client import KISApiClient
from .stock_lists import get_market_tickers
from ..ai_analysis_service import analyze_stock, get_market_trend

logger = logging.getLogger(__name__)


def convert_numpy_types(obj):
    """
    Recursively converts numpy types in a dictionary or list to native Python types.
    """
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(i) for i in obj]
    elif isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif obj is None:
        return None
    else:
        return obj


def screen_initial_stocks():
    """
    1단계: KOSPI/KOSDAQ 주요 종목을 대상으로 AI 분석을 수행하고 DB에 저장/업데이트합니다.
    """
    logger.info("1차 종목 스크리닝을 시작합니다: AI 기반 종목 분석")

    first_account = TradingAccount.objects.filter(is_active=True).first()
    if not first_account:
        logger.error("API 호출에 사용할 활성 계정이 없어 스크리닝을 중단합니다.")
        return

    client = KISApiClient(
        app_key=first_account.app_key,
        app_secret=first_account.app_secret,
        account_no=first_account.account_number,
        account_type=first_account.account_type
    )

    # 시장의 주요 우량주 목록을 기본값으로 포함
    predefined_blue_chips = [
        "005930", "000660", "005380", "005490", "035420",
        "000270", "035720", "068270", "051910", "006400"
    ]

    try:
        market_tickers = get_market_tickers()
    except Exception as e:
        logger.error(f"미리 정의된 종목 리스트를 가져오는 중 오류 발생: {e}", exc_info=True)
        market_tickers = []

    target_symbols = list(set(predefined_blue_chips + market_tickers))

    if not target_symbols:
        logger.error("분석할 대상 종목이 없어 스크리닝을 종료합니다.")
        return

    # AI 분석 전, 전체 시장 트렌드를 파악
    market_trend = get_market_trend(client)
    logger.info(f"오늘의 시장 트렌드: {market_trend}")

    logger.info(f"총 {len(target_symbols)}개 종목을 대상으로 AI 기반 필터링을 시작합니다.")

    # 분석 시작 전, 이전 데이터 초기화 (is_investable 플래그를 False로, 분석 데이터는 빈 JSON으로)
    AnalyzedStock.objects.all().update(is_investable=False, raw_analysis_data={})

    screened_count = 0
    total_symbols = len(target_symbols)
    for i, symbol in enumerate(target_symbols):
        progress = int(((i + 1) / total_symbols) * 95)
        status_text = f"AI 분석 중: {symbol} ({i + 1}/{total_symbols})"
        cache.set('screening_progress', {'status': status_text, 'progress': progress}, timeout=300)

        # AI 분석 수행
        analysis_result = analyze_stock(symbol, client, market_trend)

        if not analysis_result:
            logger.warning(f"[{symbol}] AI 분석에 실패하여 스크리닝에서 제외합니다.")
            continue

        # 현재가 및 종목명 정보 조회
        price_info_response = client.get_current_price(symbol)
        if not (price_info_response and price_info_response.is_ok()):
            logger.warning(f"[{symbol}] 현재가 정보를 가져오지 못해 처리를 건너뜁니다.")
            continue
        price_info = price_info_response.get_body().get('output', {})
        stock_name = price_info.get('hts_kor_isnm', '')
        last_price = price_info.get('stck_prpr', '0')

        # 1차: AI 분석 결과 기반 필터링
        is_investable = analysis_result.horizon in ['SHORT', 'MID']
        reason = f"AI 분석({analysis_result.horizon})"

        # 2차: 기본 자격 필터링 (ETF, 우선주 등 제외)
        if not stock_name or stock_name.endswith('우') or any(keyword in stock_name for keyword in ['스팩', 'ETN', 'TIGER', 'KODEX']):
            if is_investable: # AI는 통과했으나 기본 자격 미달
                reason += ", 기본 필터(자격 미달)"
                is_investable = False

        if is_investable:
            logger.info(f"[{symbol}] {stock_name}: 투자 가능 후보로 선정. ({reason})")
            screened_count += 1
        else:
            logger.info(f"[{symbol}] {stock_name}: 투자 부적격. ({reason})")

        # DB에 저장하기 전, numpy 타입을 표준 파이썬 타입으로 변환
        cleaned_raw_data = convert_numpy_types(analysis_result.raw_data)

        # DB에 분석 결과 저장/업데이트
        AnalyzedStock.objects.update_or_create(
            symbol=symbol,
            defaults={
                'stock_name': stock_name,
                'is_investable': is_investable,
                'investment_horizon': analysis_result.horizon, # 투자 기간 결과 저장
                'last_price': last_price,
                'raw_analysis_data': cleaned_raw_data
            }
        )

    logger.info(f"1차 스크리닝 완료. 총 {len(target_symbols)}개 중 {screened_count}개의 투자가능 후보 종목을 DB에 저장했습니다.")