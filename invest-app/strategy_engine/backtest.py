import logging
import pandas as pd
from datetime import timedelta
from decimal import Decimal
from trading.models import HistoricalPriceData
from .filters import is_financially_sound, is_blue_chip
from .technical_analysis import calculate_atr, get_price_targets

logger = logging.getLogger(__name__)

class Backtester:
    def __init__(self, start_date, end_date, initial_capital=100_000_000):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = Decimal(initial_capital)
        self.cash = self.initial_capital
        self.portfolio = {}  # {symbol: {'quantity': int, 'buy_price': Decimal, 'group': str, 'targets': dict}}
        self.trade_log = []
        self.daily_portfolio_value = []
        self.market_mode = '단기 트레이딩 모드'  # 초기 모드
        self.cash_target_ratio = Decimal('0.3') # 초기 현금 비중 목표

    def run(self):
        logger.info(f"백테스팅 시작: {self.start_date} ~ {self.end_date}")

        all_data = pd.DataFrame.from_records(
            HistoricalPriceData.objects.filter(date__gte=self.start_date, date__lte=self.end_date).order_by('date').values()
        )
        if all_data.empty:
            logger.error("백테스팅 기간에 해당하는 데이터가 없습니다.")
            return

        all_data['date'] = pd.to_datetime(all_data['date']).dt.date

        current_date = self.start_date
        while current_date <= self.end_date:
            market_data_today = all_data[all_data['date'] == current_date]
            if market_data_today.empty:
                current_date += timedelta(days=1)
                continue

            # 0. 마스터 스위치: 시장 모드 결정
            kospi_history_to_date = all_data[(all_data['symbol'] == '0001') & (all_data['date'] <= current_date)]
            self.market_mode = determine_market_mode(kospi_history_to_date.to_dict('records'))
            if self.market_mode == '단기 트레이딩 모드':
                self.cash_target_ratio = Decimal('0.3')
            else: # 우량주 분할매수 모드
                self.cash_target_ratio = Decimal('0.7')
            logger.info(f"[{current_date}] 시장 모드: {self.market_mode}, 현금 목표: {self.cash_target_ratio:%}")

            # 1. 포트폴리오 평가 및 매도 로직 실행
            self._evaluate_and_sell(current_date, all_data)

            # 2. 투자 유니버스 선정 및 매수 로직 실행
            if current_date.weekday() == 0: # 매주 월요일에만 유니버스 리밸런싱 및 매수 고려
                # 백테스팅에서는 실제 재무 데이터를 매일 조회할 수 없으므로,
                # 시가총액과 거래대금을 기준으로 '일반' 유니버스를 단순화하여 생성합니다.
                market_caps = market_data_today.groupby('symbol')['close_price'].last() * market_data_today.groupby('symbol')['volume'].last()
                top_200_symbols = market_caps.nlargest(200).index.tolist()

                # '중/장기' 종목은 더 엄격한 기준으로 필터링해야 하지만, 여기서는 예시로 일부를 선택합니다.
                general_universe = top_200_symbols[10:]
                blue_chip_universe = top_200_symbols[:10]

                self._buy_stocks(current_date, all_data, general_universe, '일반')
                self._buy_stocks(current_date, all_data, blue_chip_universe, '중/장기')

            # 3. 일일 포트폴리오 가치 기록
            self._record_daily_value(current_date, market_data_today)

            current_date += timedelta(days=1)

        self.generate_report()

    def _evaluate_and_sell(self, current_date, all_data):
        for symbol, position in list(self.portfolio.items()):
            stock_data_today = all_data[(all_data['symbol'] == symbol) & (all_data['date'] == current_date)]
            if stock_data_today.empty:
                continue

            current_price = stock_data_today.iloc[0]['close_price']

            # ATR 및 손절가/목표가 재계산
            history_to_date = all_data[(all_data['symbol'] == symbol) & (all_data['date'] <= current_date)]
            if len(history_to_date) < 14: continue

            atr = calculate_atr(history_to_date.to_dict('records'), period=14)
            if atr <= 0: continue

            price_targets = get_price_targets(atr, float(position['buy_price']), float(current_price), position['group'])

            # 매도 조건 확인
            should_sell = False
            if price_targets.get('stop_loss_price') and current_price < Decimal(price_targets['stop_loss_price']):
                should_sell = True
            elif position['group'] == '일반' and price_targets.get('target_price') and current_price > Decimal(price_targets['target_price']):
                should_sell = True

            if should_sell:
                self._execute_sell(symbol, position['quantity'], current_price, current_date)

    def _buy_stocks(self, current_date, all_data, universe, group):
        for symbol in universe:
            if symbol in self.portfolio:
                continue

            history_to_date = all_data[(all_data['symbol'] == symbol) & (all_data['date'] <= current_date)]
            if len(history_to_date) < 14: continue

            current_price = history_to_date.iloc[-1]['close_price']
            atr = calculate_atr(history_to_date.to_dict('records'), period=14)
            if atr <= 0: continue

            quantity = (self.cash * Decimal('0.05')) // current_price  # 가용 현금의 5%씩 분할 매수
            if quantity > 0:
                price_targets = get_price_targets(atr, float(current_price), float(current_price), group)
                self._execute_buy(symbol, quantity, current_price, current_date, group, price_targets)

    def _execute_buy(self, symbol, quantity, price, date, group, targets):
        cost = quantity * price
        if self.cash < cost:
            return
        self.cash -= cost
        self.portfolio[symbol] = {'quantity': quantity, 'buy_price': price, 'group': group, 'targets': targets}
        self.trade_log.append(f"{date} - BUY: {quantity} of {symbol} at {price} ({group})")
        logger.info(f"매수: {symbol}, 수량: {quantity}, 가격: {price}, 그룹: {group}")

    def _execute_sell(self, symbol, quantity, price, date):
        revenue = quantity * price
        self.cash += revenue
        del self.portfolio[symbol]
        self.trade_log.append(f"{date} - SELL: {quantity} of {symbol} at {price}")
        logger.info(f"매도: {symbol}, 수량: {quantity}, 가격: {price}")

    def _record_daily_value(self, date, market_data_today):
        holdings_value = Decimal(0)
        for symbol, position in self.portfolio.items():
            stock_data = market_data_today[market_data_today['symbol'] == symbol]
            current_price = stock_data.iloc[0]['close_price'] if not stock_data.empty else position['buy_price']
            holdings_value += position['quantity'] * current_price

        total_value = self.cash + holdings_value
        self.daily_portfolio_value.append({'date': date, 'value': total_value})

    def generate_report(self):
        final_value = self.daily_portfolio_value[-1]['value']
        cagr = ((final_value / self.initial_capital) ** (Decimal('365.0') / len(self.daily_portfolio_value)) - 1) * 100

        print("\n--- 백테스팅 결과 ---")
        print(f"기간: {self.start_date} ~ {self.end_date}")
        print(f"초기 자본: {self.initial_capital:,.0f} 원")
        print(f"최종 자산: {final_value:,.0f} 원")
        print(f"총 수익률: {(final_value / self.initial_capital - 1) * 100:.2f}%")
        print(f"연평균 복리 수익률 (CAGR): {cagr:.2f}%")
        # TODO: MDD (최대 낙폭) 계산 로직 추가
        print("--------------------")
        print("거래 내역:")
        for log in self.trade_log:
            print(log)