import logging
import time
from decimal import Decimal
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

    def screen_all_stocks(self, api_delay=0.5):
        """
        전체 종목을 대상으로 스크리닝을 실행하고 결과를 DB에 저장합니다.
        API 호출 제한을 피하기 위해 각 종목 처리 후 지연 시간을 둡니다.
        """
        logger.info("전체 종목 스크리닝을 시작합니다.")

        # 1. 전체 종목 코드 가져오기 (로컬 .mst 파일 사용)
        all_stocks_map = self.client.get_all_stock_codes()
        if not all_stocks_map:
            logger.error("스크리닝을 위한 종목 코드를 가져오지 못했습니다. .mst 파일 설정을 확인하세요.")
            return 0
        all_symbols = list(all_stocks_map.keys())

        logger.info(f"총 {len(all_symbols)}개의 종목을 대상으로 스크리닝을 진행합니다.")

        screened_count = 0
        for i, symbol in enumerate(all_symbols):
            try:
                # API 호출 지연
                time.sleep(api_delay)

                # 2. 필요한 데이터 수집
                # get_stock_info가 가장 많은 정보를 주므로 먼저 호출
                info_res = self.client.get_stock_info(symbol)
                if not (info_res and info_res.is_ok()):
                    logger.debug(f"[{symbol}] 기본 정보 수집 실패. 건너뜁니다.")
                    continue
                stock_info = info_res.get_body().get('output', {})

                price_res = self.client.get_current_price(symbol)
                fin_res = self.client.get_financial_info(symbol)
                history_res = self.client.get_daily_price_history(symbol, days=30) # 20일 평균 거래대금 계산용

                if not (price_res and price_res.is_ok() and fin_res and fin_res.is_ok() and history_res and history_res.is_ok()):
                    logger.warning(f"[{symbol}] 추가 데이터(가격/재무/히스토리) 수집 실패. 건너뜁니다.")
                    continue

                price_data = price_res.get_body().get('output', {})
                financial_data = fin_res.get_body().get('output', [])
                history_data = history_res.get_body().get('output2', [])

                # 3. 필터링에 필요한 데이터 가공
                # 20일 평균 거래대금 계산
                if len(history_data) >= 20:
                    avg_20d_turnover = sum(int(d['acml_tr_pbmn']) for d in history_data[-20:]) / 20
                else:
                    avg_20d_turnover = 0 # 데이터 부족 시 0으로 처리

                # 시가총액 계산
                listed_shares = int(stock_info.get('stck_iss_cnt', '0'))
                current_price = int(price_data.get('stck_prpr', '0'))
                market_cap = listed_shares * current_price

                stock_details = {
                    'symbol': symbol,
                    'stock_name': stock_info.get('prdt_abrv_name', all_stocks_map.get(symbol, '')),
                    'avg_20d_turnover': avg_20d_turnover,
                    'market_cap': market_cap,
                    'sector_code': stock_info.get('bstp_larg_div_code'),
                    'is_admin_issue': price_data.get('admd_item_yn', 'N') == 'Y',
                    'is_investment_alert': any(price_data.get(key, 'N') == 'Y' for key in ['invt_alrm_yn', 'invt_atn_yn', 'invt_dngr_yn']),
                    'is_capital_impaired': stock_info.get('cpta_eros_yn', 'N') == 'Y',
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