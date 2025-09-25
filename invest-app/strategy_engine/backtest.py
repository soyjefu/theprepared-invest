import logging
import pandas as pd
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from trading.kis_client import KISApiClient
from .models import HistoricalPrice
from trading.trading_service import DailyTrader

logger = logging.getLogger(__name__)

class MockKISApiClient(KISApiClient):
    """
    백테스팅을 위한 KISApiClient의 모의(Mock) 버전.
    실제 API를 호출하는 대신, DB에 저장된 과거 시세 데이터를 사용하고
    가상의 계좌 잔고를 관리합니다.
    """
    def __init__(self, backtester):
        self.backtester = backtester
        # 실제 API 호출에 필요한 정보는 없으므로 None으로 설정
        super().__init__(app_key=None, app_secret=None, account_no=None, account_type='SIM')

    def get_account_balance(self):
        # 가상 계좌의 잔고를 API 응답 형식으로 반환
        output1 = []
        for symbol, data in self.backtester.portfolio.items():
            current_price = self.backtester.get_price(symbol, self.backtester.current_date)
            output1.append({
                'pdno': symbol,
                'hldg_qty': str(data['quantity']),
                'pchs_amt': str(data['quantity'] * data['buy_price']),
                'evlu_amt': str(data['quantity'] * current_price),
            })

        output2 = [{
            'dnca_tot_amt': str(self.backtester.cash),
            'tot_evlu_amt': str(self.backtester.get_total_value()),
        }]

        # KISAPIResponse와 유사한 객체를 반환하도록 구조화
        class MockResponse:
            def is_ok(self): return True
            def get_body(self): return {'output1': output1, 'output2': output2}
            def get_error_message(self): return ""
        return MockResponse()

    def get_current_price(self, symbol):
        price = self.backtester.get_price(symbol, self.backtester.current_date)
        class MockResponse:
            def is_ok(self): return price > 0
            def get_body(self): return {'output': {'stck_prpr': str(price)}}
            def get_error_message(self): return "Price not found" if price == 0 else ""
        return MockResponse()

    def get_index_price_history(self, symbol, days):
        start = self.backtester.current_date - timedelta(days=days)
        history = self.backtester.get_history(symbol, start, self.backtester.current_date)
        class MockResponse:
            def is_ok(self): return bool(history)
            def get_body(self): return {'output2': history}
            def get_error_message(self): return ""
        return MockResponse()

    def place_order(self, account, symbol, quantity, price, order_type, fee_rate=0.0):
        if order_type == 'BUY':
            self.backtester._execute_buy(symbol, quantity, Decimal(price), self.backtester.current_date)
        elif order_type == 'SELL':
            self.backtester._execute_sell(symbol, quantity, Decimal(price), self.backtester.current_date)

        class MockResponse:
            def is_ok(self): return True
            def get_body(self): return {'rt_cd': '0'}
        return MockResponse()

class Backtester:
    def __init__(self, user, start_date, end_date, initial_capital=100_000_000, strategy_params=None):
        self.user = user
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = Decimal(initial_capital)
        self.strategy_params = strategy_params if strategy_params is not None else {}

        self.cash = self.initial_capital
        self.portfolio = {}  # {symbol: {'quantity': int, 'buy_price': Decimal}}
        self.trade_log = []
        self.daily_portfolio_value = []
        self.current_date = start_date
        self.all_history_data = self._load_all_data()

    def _load_all_data(self):
        logger.info("백테스팅에 필요한 모든 시세 데이터를 로딩합니다...")
        qs = HistoricalPrice.objects.filter(date__gte=self.start_date, date__lte=self.end_date).order_by('date')
        df = pd.DataFrame.from_records(qs.values())
        if df.empty:
            return df
        df['date'] = pd.to_datetime(df['date'])
        # 빠른 조회를 위해 multi-index 설정
        df.set_index(['date', 'symbol'], inplace=True)
        return df

    def get_price(self, symbol, date):
        try:
            return self.all_history_data.loc[(pd.Timestamp(date), symbol), 'close_price']
        except KeyError:
            return 0

    def get_history(self, symbol, start, end):
        try:
            df_slice = self.all_history_data.loc[(pd.Timestamp(start)):(pd.Timestamp(end)), :]
            symbol_history = df_slice[df_slice.index.get_level_values('symbol') == symbol]
            # API 응답 형식과 유사하게 변환
            return [{'stck_bsop_date': d.strftime('%Y%m%d'), 'stck_clpr': str(p)} for d, p in symbol_history['close_price'].items()]
        except KeyError:
            return []

    def get_total_value(self):
        holdings_value = Decimal(0)
        for symbol, position in self.portfolio.items():
            price = self.get_price(symbol, self.current_date)
            if price > 0:
                holdings_value += position['quantity'] * price
        return self.cash + holdings_value

    def run(self):
        logger.info(f"백테스팅 시작: {self.start_date} ~ {self.end_date}")

        if self.all_history_data.empty:
            logger.error("백테스팅 기간에 해당하는 데이터가 없습니다.")
            return None

        # DailyTrader를 생성하고 Mock Client 주입
        trader = DailyTrader(user=self.user)
        trader.client = MockKISApiClient(self)

        # 사용자 정의 파라미터가 있으면 DailyTrader의 속성을 덮어쓰기
        for param, value in self.strategy_params.items():
            if hasattr(trader, param):
                logger.info(f"Overriding DailyTrader parameter: {param} = {value}")
                setattr(trader, param, Decimal(value)) # 파라미터를 Decimal로 변환

        while self.current_date <= self.end_date:
            # DailyTrader의 로직 실행
            trader.run_daily_trading()

            # 일일 포트폴리오 가치 기록
            self.daily_portfolio_value.append({
                'date': self.current_date,
                'value': self.get_total_value()
            })
            self.current_date += timedelta(days=1)

        return self.generate_report()

    def _execute_buy(self, symbol, quantity, price, date):
        cost = quantity * price
        fee = cost * Decimal(str(settings.TRADING_FEE_RATE))
        total_cost = cost + fee

        if self.cash < total_cost:
            logger.warning(f"[{date}] 현금 부족으로 {symbol} 매수 실패. 필요: {total_cost}, 보유: {self.cash}")
            return

        self.cash -= total_cost

        # 포트폴리오에 추가 또는 수량 업데이트
        if symbol in self.portfolio:
            current_qty = self.portfolio[symbol]['quantity']
            current_avg_price = self.portfolio[symbol]['buy_price']
            new_avg_price = (current_avg_price * current_qty + price * quantity) / (current_qty + quantity)
            self.portfolio[symbol]['quantity'] += quantity
            self.portfolio[symbol]['buy_price'] = new_avg_price
        else:
            self.portfolio[symbol] = {'quantity': quantity, 'buy_price': price}

        self.trade_log.append({
            'date': date, 'type': 'BUY', 'symbol': symbol,
            'quantity': quantity, 'price': price
        })

    def _execute_sell(self, symbol, quantity, price, date):
        if symbol not in self.portfolio or self.portfolio[symbol]['quantity'] < quantity:
            logger.warning(f"[{date}] 매도할 {symbol} 수량 부족.")
            return

        revenue = quantity * price
        fee = revenue * Decimal(str(settings.TRADING_FEE_RATE))
        tax = revenue * Decimal(str(settings.TRADING_TAX_RATE))
        net_revenue = revenue - fee - tax

        self.cash += net_revenue

        buy_price = self.portfolio[symbol]['buy_price']
        profit = (price - buy_price) * quantity - (fee + tax)

        self.portfolio[symbol]['quantity'] -= quantity
        if self.portfolio[symbol]['quantity'] == 0:
            del self.portfolio[symbol]

        self.trade_log.append({
            'date': date, 'type': 'SELL', 'symbol': symbol,
            'quantity': quantity, 'price': price, 'profit': profit
        })

    def generate_report(self):
        if not self.daily_portfolio_value:
            return {"error": "No data to generate report."}

        df = pd.DataFrame(self.daily_portfolio_value)
        df['value'] = pd.to_numeric(df['value'])
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)

        # CAGR
        final_value = df['value'].iloc[-1]
        days = (self.end_date - self.start_date).days
        cagr = ((final_value / self.initial_capital) ** (Decimal('365.0') / days) - 1) * 100 if days > 0 else Decimal(0)

        # MDD
        peak = df['value'].cummax()
        drawdown = (df['value'] - peak) / peak
        mdd = drawdown.min() * 100

        # Sharpe Ratio (연율화)
        df['daily_return'] = df['value'].pct_change()
        sharpe_ratio = (df['daily_return'].mean() / df['daily_return'].std()) * (Decimal('252') ** Decimal('0.5')) if df['daily_return'].std() != 0 else Decimal(0)

        # 승률
        sell_trades = [t for t in self.trade_log if t['type'] == 'SELL']
        wins = sum(1 for t in sell_trades if t['profit'] > 0)
        total_trades = len(sell_trades)
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0

        report = {
            "start_date": self.start_date.strftime('%Y-%m-%d'),
            "end_date": self.end_date.strftime('%Y-%m-%d'),
            "initial_capital": f"{self.initial_capital:,.0f} KRW",
            "final_value": f"{final_value:,.0f} KRW",
            "cagr": f"{cagr:.2f}%",
            "mdd": f"{mdd:.2f}%",
            "sharpe_ratio": f"{sharpe_ratio:.2f}",
            "win_rate": f"{win_rate:.2f}%",
            "total_trades": total_trades,
            "trade_log": self.trade_log,
            "daily_values": df.reset_index().to_dict('records')
        }

        logger.info("--- 백테스팅 결과 ---")
        for key, value in report.items():
            if key not in ['trade_log', 'daily_values']:
                logger.info(f"{key.replace('_', ' ').title()}: {value}")

        return report