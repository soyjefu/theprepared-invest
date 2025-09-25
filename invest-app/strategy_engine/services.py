import logging
from trading.kis_client import KISApiClient
from trading.models import TradingAccount, AnalyzedStock
from .filters import is_financially_sound, is_blue_chip
from .technical_analysis import calculate_atr, get_price_targets

logger = logging.getLogger(__name__)

class UniverseScreener:
    """
    전체 상장 종목을 대상으로 유니버스 필터링 로직을 수행하고,
    결과를 데이터베이스에 저장하는 서비스 클래스.
    """
    def __init__(self, user, account_number=None):
        """
        Screener를 초기화합니다. 특정 계좌번호가 주어지지 않으면,
        사용자의 활성화된 첫 번째 계좌를 사용합니다.
        """
        try:
            if account_number:
                self.account = TradingAccount.objects.get(user=user, account_number=account_number, is_active=True)
            else:
                self.account = TradingAccount.objects.filter(user=user, is_active=True).first()

            if not self.account:
                raise TradingAccount.DoesNotExist

            self.client = KISApiClient(
                app_key=self.account.app_key,
                app_secret=self.account.app_secret,
                account_no=self.account.account_number,
                account_type=self.account.get_account_type_display()
            )
        except TradingAccount.DoesNotExist:
            logger.error(f"Screener 초기화 실패: {user.username} 사용자의 유효한 트레이딩 계좌를 찾을 수 없습니다.")
            raise
        except Exception as e:
            logger.error(f"KISApiClient 초기화 중 에러 발생: {e}")
            raise

    def screen_all_stocks(self):
        """
        전체 종목을 대상으로 스크리닝을 실행하고 결과를 DB에 저장합니다.
        """
        logger.info("전체 종목 스크리닝을 시작합니다.")

        # 1. 전체 종목 코드 가져오기 (API 또는 로컬 파일)
        # 참고: get_all_stock_codes는 .mst 파일에 의존하므로, API 기반의 다른 방법이 더 안정적일 수 있습니다.
        # 여기서는 예시로 `get_top_volume_stocks`를 사용하지만, 실제로는
        # KIS에서 제공하는 전체 종목 리스트 API를 사용해야 합니다. (예: FHPST01740000 - 시가총액 순위)
        # 지금은 기능 구현을 위해 거래량 상위 200개 종목으로 제한하여 테스트합니다.
        kospi_stocks = self.client.get_top_volume_stocks(market='KOSPI', top_n=100)
        kosdaq_stocks = self.client.get_top_volume_stocks(market='KOSDAQ', top_n=100)
        all_symbols = list(set(kospi_stocks + kosdaq_stocks))

        logger.info(f"총 {len(all_symbols)}개의 종목을 대상으로 스크리닝을 진행합니다.")

        screened_count = 0
        for symbol in all_symbols:
            try:
                # 2. 필요한 데이터 수집
                price_res = self.client.get_current_price(symbol)
                fin_res = self.client.get_financial_info(symbol)
                info_res = self.client.get_stock_info(symbol)

                if not (price_res and price_res.is_ok() and fin_res and fin_res.is_ok() and info_res and info_res.is_ok()):
                    logger.warning(f"[{symbol}] 데이터 수집 실패. 건너뜁니다.")
                    continue

                price_data = price_res.get_body().get('output', {})
                financial_data = fin_res.get_body().get('output', [])
                stock_info = info_res.get_body().get('output', {})

                # 3. 필터링에 필요한 데이터 가공
                stock_details = {
                    'symbol': symbol,
                    'stock_name': stock_info.get('prdt_abrv_name'),
                    'avg_20d_turnover': int(price_data.get('acml_tr_pbmn', '0')), # 20일 평균 대신 누적 거래대금으로 대체
                    'market_cap': int(price_data.get('hbid_uplmt_price', '0')) * int(price_data.get('stck_prpr', '0')), # 시총 임시 계산
                    'sector_code': stock_info.get('bstp_larg_div_code'), # KRX 업종 대분류 코드
                    'is_admin_issue': price_data.get('admd_item_yn', 'N') == 'Y',
                    'is_investment_alert': price_data.get('invt_alrm_yn', 'N') == 'Y',
                    'is_capital_impaired': False, # 이 정보는 별도 API 필요
                }

                # 4. 필터링 로직 실행
                is_sound, reason_sound = is_financially_sound(stock_details, financial_data)
                if not is_sound:
                    logger.debug(f"[{symbol}] '일반' 종목 필터링 실패: {reason_sound}")
                    continue

                is_blue, reason_blue = is_blue_chip(stock_details, financial_data)

                investment_horizon = '일반'
                if is_blue:
                    investment_horizon = '중/장기'

                # 5. ATR 및 목표/손절가 계산
                price_targets = {}
                daily_history_res = self.client.get_daily_price_history(symbol, days=30)
                if daily_history_res and daily_history_res.is_ok():
                    daily_history = daily_history_res.get_body().get('output2', [])
                    current_price = float(price_data.get('stck_prpr', '0'))

                    atr = calculate_atr(daily_history, period=14)
                    if atr > 0:
                        # 매수가는 현재가로 가정하여 계산
                        price_targets = get_price_targets(atr, current_price, current_price, investment_horizon)

                # 6. 분석 결과 데이터베이스에 저장/업데이트
                AnalyzedStock.objects.update_or_create(
                    symbol=symbol,
                    defaults={
                        'stock_name': stock_details['stock_name'],
                        'is_investable': True,
                        'investment_horizon': investment_horizon,
                        'last_price': Decimal(price_data.get('stck_prpr', '0')),
                        'raw_analysis_data': {
                            'filter_sound_reason': reason_sound,
                            'filter_blue_chip_reason': reason_blue,
                            'details': stock_details,
                            'financials': financial_data,
                            'atr': atr,
                            'price_targets': price_targets
                        }
                    }
                )
                screened_count += 1
                logger.info(f"[{symbol}] 스크리닝 통과. 등급: {investment_horizon}, ATR: {atr:.2f}, 목표가: {price_targets}")

            except Exception as e:
                logger.error(f"[{symbol}] 스크리닝 중 예외 발생: {e}", exc_info=True)

        logger.info(f"종목 스크리닝 완료. 총 {len(all_symbols)}개 중 {screened_count}개 종목이 유니버스에 포함되었습니다.")
        return screened_count