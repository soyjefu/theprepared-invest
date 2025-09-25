import logging
from decimal import Decimal
import pandas as pd
from django.conf import settings
from .kis_client import KISApiClient
from .models import TradingAccount, Portfolio, AnalyzedStock
from strategy_engine.filters import determine_market_mode

logger = logging.getLogger(__name__)

class DailyTrader:
    """
    일일 자동 매매 로직을 실행하는 서비스 클래스.
    시장 모드를 판단하고, 보유 종목을 관리하며, 신규 주문을 생성합니다.
    """
    def __init__(self, user, account_number=None):
        """
        DailyTrader를 초기화합니다.

        Args:
            user (User): 매매를 실행할 사용자 객체.
            account_number (str, optional): 사용할 특정 계좌 번호.
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

            # DB에서 전략 설정값 불러오기
            strategy_settings = StrategySettings.get_solo()
            self.fee_rate = strategy_settings.trading_fee_rate
            self.tax_rate = strategy_settings.trading_tax_rate
            self.risk_per_trade = strategy_settings.risk_per_trade
            self.max_total_risk = strategy_settings.max_total_risk
            self.dca_base_amount = strategy_settings.dca_base_amount
            self.dca_settings = strategy_settings.dca_settings_json

            logger.info(f"DailyTrader for account {self.account.account_number} initialized.")

        except TradingAccount.DoesNotExist:
            logger.error(f"DailyTrader 초기화 실패: {user.username} 사용자의 유효한 트레이딩 계좌를 찾을 수 없습니다.")
            raise

    def run_daily_trading(self):
        """
        일일 매매 프로세스 전체를 실행합니다.
        """
        logger.info("Starting daily trading process...")

        # 1. 시장 모드 판단
        market_mode, kospi_history = self.get_market_mode()
        logger.info(f"Current market mode: {market_mode}")

        # 2. 보유 종목 매도 조건 확인 및 처리
        self.manage_open_positions()

        # 3. 시장 모드에 따른 신규 매수 처리
        if market_mode == '단기 트레이딩 모드':
            self.execute_short_term_buys()
        elif market_mode == '우량주 분할매수 모드':
            self.execute_dca_buys(kospi_history=kospi_history)

        logger.info("Daily trading process finished.")

    def get_market_mode(self):
        """
        코스피 지수와 이동평균선을 비교하여 현재 시장 모드를 결정하고, 사용된 데이터도 함께 반환합니다.
        """
        # 60일(시장모드)과 120일(DCA) 이평선을 모두 계산하기 위해 넉넉하게 200일치 요청
        kospi_history_res = self.client.get_index_price_history(symbol='0001', days=200)
        if not (kospi_history_res and kospi_history_res.is_ok()):
            logger.warning("Failed to fetch KOSPI history for market mode. Defaulting to '단기 트레이딩 모드'.")
            return '단기 트레이딩 모드', []

        kospi_history = kospi_history_res.get_body().get('output2', [])
        market_mode = determine_market_mode(kospi_history)
        return market_mode, kospi_history

    def manage_open_positions(self):
        """
        보유 종목을 확인하고 매도 조건을 검사하여 매도 주문을 실행합니다.
        '일반' 종목은 고정 목표/손절가를, '중/장기' 종목은 트레일링 스탑을 적용합니다.
        """
        logger.info("Checking open positions for potential sells...")
        balance_res = self.client.get_account_balance()
        if not (balance_res and balance_res.is_ok()):
            logger.error("Failed to get account balance. Cannot manage open positions.")
            return

        holdings = balance_res.get_body().get('output1', [])
        if not holdings:
            logger.info("No open positions found.")
            return

        for stock in holdings:
            symbol = stock.get('pdno')
            try:
                analyzed_stock = AnalyzedStock.objects.get(symbol=symbol)
                if not analyzed_stock.is_investable:
                    continue

                current_price_res = self.client.get_current_price(symbol)
                if not (current_price_res and current_price_res.is_ok()):
                    logger.warning(f"[{symbol}] Failed to get current price. Skipping sell check.")
                    continue

                current_price = Decimal(current_price_res.get_body().get('output', {}).get('stck_prpr', '0'))
                if current_price == 0:
                    continue

                horizon = analyzed_stock.investment_horizon
                targets = analyzed_stock.raw_analysis_data.get('price_targets', {})
                target_price = Decimal(targets.get('target_price', '0'))
                stop_loss_price = Decimal(targets.get('stop_loss_price', '0'))

                should_sell = False
                sell_reason = ""

                if horizon == '일반':
                    if target_price > 0 and current_price >= target_price:
                        should_sell = True
                        sell_reason = f"target price ({target_price}) reached"
                    elif stop_loss_price > 0 and current_price <= stop_loss_price:
                        should_sell = True
                        sell_reason = f"stop-loss price ({stop_loss_price}) triggered"

                elif horizon == '중/장기':
                    # '중/장기'는 트레일링 스탑만 확인 (목표가 없음)
                    if stop_loss_price > 0 and current_price <= stop_loss_price:
                        should_sell = True
                        sell_reason = f"trailing stop-loss ({stop_loss_price}) triggered"

                if should_sell:
                    quantity_to_sell = int(stock.get('hldg_qty', '0'))
                    logger.info(f"SELL SIGNAL for {symbol}: {sell_reason}. Attempting to sell {quantity_to_sell} shares.")
                    self.client.place_order(
                        account=self.account,
                        symbol=symbol,
                        quantity=quantity_to_sell,
                        price=int(current_price), # 지정가 주문
                        order_type='SELL',
                        fee_rate=self.fee_rate
                    )

            except AnalyzedStock.DoesNotExist:
                logger.warning(f"[{symbol}] No analysis data found in AnalyzedStock. Cannot manage this position.")
            except Exception as e:
                logger.error(f"Error managing position for {symbol}: {e}", exc_info=True)

    def execute_short_term_buys(self):
        """
        '단기 트레이딩 모드'의 매수 로직을 실행합니다.
        2단계 리스크 관리(포트폴리오 총 리스크, 개별 종목 리스크)를 적용합니다.
        """
        logger.info("Executing short-term buy logic...")

        # 1. 현재 계좌 정보 확인
        balance_res = self.client.get_account_balance()
        if not (balance_res and balance_res.is_ok()):
            logger.error("Failed to get account balance. Cannot execute buys.")
            return

        balance_body = balance_res.get_body()
        holdings = balance_body.get('output1', [])
        total_asset_value = Decimal(balance_body.get('output2', [{}])[0].get('tot_evlu_amt', '0'))

        # 2. 포트폴리오 총 리스크 확인
        num_open_positions = len(holdings)
        potential_total_risk = (num_open_positions + 1) * self.risk_per_trade

        if potential_total_risk > self.max_total_risk:
            logger.warning(f"Total portfolio risk limit exceeded. "
                           f"Current positions: {num_open_positions}, "
                           f"Potential risk: {potential_total_risk:.2%}, "
                           f"Limit: {self.max_total_risk:.2%}. "
                           f"Skipping new buy orders.")
            return

        # 3. 매수 후보 종목 선정 ('일반' 태그, 아직 보유하지 않은 종목)
        held_symbols = [stock['pdno'] for stock in holdings]
        buy_candidates = AnalyzedStock.objects.filter(
            is_investable=True,
            investment_horizon='일반'
        ).exclude(symbol__in=held_symbols).order_by('-updated_at') # 최신 분석 순

        if not buy_candidates:
            logger.info("No new '일반' buy candidates found.")
            return

        # 이 단계에서는 가장 유력한 후보 1개만 매수 시도
        candidate = buy_candidates.first()

        try:
            # 4. 투자 금액 계산 (ATR 기반 리스크 균등)
            atr = Decimal(candidate.raw_analysis_data.get('atr', '0'))
            stop_loss_multiplier = 2 # '일반' 종목의 손절 ATR 배수

            if atr <= 0:
                logger.warning(f"[{candidate.symbol}] ATR is zero or invalid. Cannot calculate position size.")
                return

            # 리스크 금액 = 총 자산 * 개별 종목 리스크 비율
            risk_amount_per_trade = total_asset_value * Decimal(self.risk_per_trade)

            # 1주당 예상 손실액 (손절 시) = (매수가 - 손절가) + 매수수수료 + 매도수수료 + 매도세금
            buy_price = candidate.last_price
            stop_loss_price = buy_price - (atr * stop_loss_multiplier)

            loss_per_share = buy_price - stop_loss_price
            buy_fee = buy_price * Decimal(self.fee_rate)
            sell_fee = stop_loss_price * Decimal(self.fee_rate)
            sell_tax = stop_loss_price * Decimal(self.tax_rate)

            total_risk_per_share = loss_per_share + buy_fee + sell_fee + sell_tax

            if total_risk_per_share <= 0:
                 logger.warning(f"[{candidate.symbol}] Calculated risk per share is zero or negative. Skipping.")
                 return

            # 매수 수량 = 리스크 금액 / 1주당 총 리스크
            position_size = int(risk_amount_per_trade / total_risk_per_share)

            if position_size == 0:
                logger.info(f"[{candidate.symbol}] Calculated position size is zero. Skipping buy.")
                return

            # 5. 매수 주문 실행
            logger.info(f"BUY SIGNAL for {candidate.symbol}. Position size: {position_size} shares based on risk management.")
            self.client.place_order(
                account=self.account,
                symbol=candidate.symbol,
                quantity=position_size,
                price=int(candidate.last_price), # 분석 시점의 가격으로 지정가 주문
                order_type='BUY',
                fee_rate=self.fee_rate
            )
        except Exception as e:
            logger.error(f"Error executing buy for {candidate.symbol}: {e}", exc_info=True)

    def execute_dca_buys(self, kospi_history: list):
        """
        '우량주 분할매수 모드'의 매수 로직을 실행합니다.
        코스피 지수 하락률에 따라 매수 금액을 조절하는 동적 DCA 전략을 사용합니다.
        """
        logger.info("Executing dynamic DCA buy logic...")

        # 1. 전달받은 코스피 데이터로 이평선 계산
        ma_period = self.dca_settings['KOSPI_MA_PERIOD']
        if len(kospi_history) < ma_period:
            logger.warning(f"Not enough KOSPI data to calculate {ma_period}-day MA for DCA. Skipping buys.")
            return

        df = pd.DataFrame(kospi_history)
        df['close'] = pd.to_numeric(df['stck_clpr'])
        df[f'ma_{ma_period}'] = df['close'].rolling(window=ma_period).mean()

        current_kospi = df['close'].iloc[-1]
        current_ma = df[f'ma_{ma_period}'].iloc[-1]

        # 2. 매수 배율 결정
        fall_rate = (current_ma - current_kospi) / current_ma if current_ma > 0 else 0
        buy_multiplier = 1.0 # 기본 배율

        # 하락률이 큰 순서대로 트리거 확인
        for trigger in sorted(self.dca_settings['TRIGGERS'], key=lambda x: x['fall_rate'], reverse=True):
            if fall_rate >= trigger['fall_rate']:
                buy_multiplier = trigger['multiplier']
                break

        logger.info(f"KOSPI fall rate from {ma_period}MA: {fall_rate:.2%}. Buy multiplier set to {buy_multiplier}x.")

        # 3. 매수 대상 선정 (기존 보유 종목 추가 매수 또는 신규 매수)
        balance_res = self.client.get_account_balance()
        if not (balance_res and balance_res.is_ok()):
            logger.error("Failed to get account balance for DCA. Cannot execute buys.")
            return

        holdings = balance_res.get_body().get('output1', [])

        # 보유 중인 '중/장기' 종목 찾기
        blue_chip_holdings = []
        if holdings:
            held_symbols = [stock['pdno'] for stock in holdings]
            analyzed_map = {s.symbol: s for s in AnalyzedStock.objects.filter(symbol__in=held_symbols)}

            for stock in holdings:
                analyzed = analyzed_map.get(stock['pdno'])
                if analyzed and analyzed.investment_horizon == '중/장기':
                    stock['pchs_amt'] = Decimal(stock['pchs_amt']) # 매입금액 Decimal로 변환
                    blue_chip_holdings.append(stock)

        buy_candidate_symbol = None

        if blue_chip_holdings:
            # 평가금액이 가장 작은 보유 우량주를 추가 매수 대상으로 선정
            buy_candidate_holding = min(blue_chip_holdings, key=lambda x: x['pchs_amt'])
            buy_candidate_symbol = buy_candidate_holding['pdno']
            logger.info(f"DCA target found from existing holdings: {buy_candidate_symbol} (Purchase amount: {buy_candidate_holding['pchs_amt']})")
        else:
            # 보유 중인 우량주가 없으면, 신규 후보를 찾음
            new_candidate = AnalyzedStock.objects.filter(
                is_investable=True,
                investment_horizon='중/장기'
            ).exclude(symbol__in=[s['pdno'] for s in holdings]).order_by('-updated_at').first()
            if new_candidate:
                buy_candidate_symbol = new_candidate.symbol
                logger.info(f"New DCA target found: {buy_candidate_symbol}")

        if not buy_candidate_symbol:
            logger.info("No '중/장기' buy candidates found (neither existing nor new).")
            return

        # 4. 최종 매수 금액 및 수량 계산
        final_investment_amount = Decimal(self.dca_base_amount) * Decimal(buy_multiplier)

        # 매수 대상의 현재가 조회
        price_res = self.client.get_current_price(buy_candidate_symbol)
        if not (price_res and price_res.is_ok()):
            logger.warning(f"[{buy_candidate_symbol}] Failed to get current price for DCA buy. Skipping.")
            return
        current_price = Decimal(price_res.get_body().get('output', {}).get('stck_prpr', '0'))

        if current_price <= 0:
            logger.warning(f"[{buy_candidate_symbol}] Invalid current price ({current_price}). Skipping DCA buy.")
            return

        quantity_to_buy = int(final_investment_amount // current_price)

        if quantity_to_buy == 0:
            logger.info(f"[{buy_candidate_symbol}] Calculated buy quantity is zero for amount {final_investment_amount}. Skipping.")
            return

        # 5. 매수 주문 실행
        logger.info(f"DCA BUY SIGNAL for {buy_candidate_symbol}. "
                    f"Amount: {final_investment_amount}, Quantity: {quantity_to_buy}")
        self.client.place_order(
            account=self.account,
            symbol=buy_candidate_symbol,
            quantity=quantity_to_buy,
            price=int(current_price),
            order_type='BUY',
            fee_rate=self.fee_rate
        )