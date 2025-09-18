# invest-app/trading/analysis/market_scanner.py

import logging
from django.core.cache import cache
from trading.models import AnalyzedStock, TradingAccount
from trading.kis_client import KISApiClient

logger = logging.getLogger(__name__)

def screen_initial_stocks():
    """
    1단계: 거래량 상위 종목을 대상으로 기본적인 필터링을 수행하고 DB에 저장/업데이트합니다.
    """
    logger.info("1차 종목 스크리닝을 시작합니다: 거래량 상위 종목 필터링")
    
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

    # 시장의 주요 우량주 목록을 기본값으로 포함하여, 장 마감 후에도 분석이 가능하도록 함
    predefined_blue_chips = [
        "005930",  # 삼성전자
        "000660",  # SK하이닉스
        "005380",  # 현대차
        "005490",  # POSCO홀딩스
        "035420",  # NAVER
        "000270",  # 기아
        "035720",  # 카카오
        "068270",  # 셀트리온
        "051910",  # LG화학
        "006400",  # 삼성SDI
    ]

    # KIS API를 통해 거래량 상위 종목을 가져옵니다.
    try:
        kospi_top = client.get_top_volume_stocks(market='KOSPI', top_n=50)
        kosdaq_top = client.get_top_volume_stocks(market='KOSDAQ', top_n=50)
        top_volume_stocks = kospi_top + kosdaq_top
    except Exception as e:
        logger.warning(f"API를 통해 거래량 상위 종목을 가져오는 중 오류 발생: {e}. 미리 정의된 종목으로 분석을 계속합니다.")
        top_volume_stocks = []

    # 두 목록을 합치고 중복을 제거합니다.
    target_symbols = list(set(predefined_blue_chips + top_volume_stocks))

    if not target_symbols:
        logger.error("분석할 대상 종목이 없어 스크리닝을 종료합니다.")
        return

    logger.info(f"거래량 상위 {len(target_symbols)}개 종목을 대상으로 1차 필터링을 시작합니다.")
    
    # DB에 저장된 모든 종목을 '투자가치 없음'으로 초기화
    AnalyzedStock.objects.all().update(is_investable=False)
    
    screened_count = 0
    total_symbols = len(target_symbols)
    for i, symbol in enumerate(target_symbols):
        # Update progress
        progress = int(((i + 1) / total_symbols) * 95)  # Go up to 95%
        status_text = f"종목 필터링 중: {symbol} ({i + 1}/{total_symbols})"
        cache.set('screening_progress', {'status': status_text, 'progress': progress}, timeout=300)

        # 현재가 조회를 통해 종목명 가져오기 및 기본 필터링
        price_info_response = client.get_current_price(symbol)
        if not (price_info_response and price_info_response.is_ok()):
            logger.warning(f"[{symbol}] 현재가 정보를 가져오지 못해 필터링에서 제외합니다. "
                           f"Error: {price_info_response.get_error_message() if price_info_response else 'No response'}")
            continue

        price_info = price_info_response.get_body()
        stock_name = price_info.get('output', {}).get('hts_kor_isnm', '')

        is_investable = True
        reason = ""

        if not stock_name or stock_name.endswith('우') or any(keyword in stock_name for keyword in ['스팩', 'ETN', 'TIGER', 'KODEX']):
            is_investable = False
            reason = "정보 없음/우선주/스팩/ETF"

        # TODO: 향후 API를 통해 관리종목 여부 등을 직접 확인하는 로직으로 고도화

        obj, created = AnalyzedStock.objects.update_or_create(
            symbol=symbol,
            defaults={
                'stock_name': stock_name,
                'is_investable': is_investable,
                'last_price': price_info.get('output', {}).get('stck_prpr', '0')
            }
        )

        if is_investable:
            screened_count += 1
        else:
            logger.debug(f"[{symbol}] {stock_name}: 필터링됨 ({reason}).")

    logger.info(f"1차 스크리닝 완료. 총 {len(target_symbols)}개 중 {screened_count}개의 투자가능 후보 종목을 DB에 저장했습니다.")