from django.test import TestCase
import pandas as pd
from strategy_engine.technical_analysis import calculate_atr

class TechnicalAnalysisTest(TestCase):
    def setUp(self):
        # More realistic data with some volatility
        self.daily_price_history = [
            {'stck_hgpr': '10500', 'stck_lwpr': '10000', 'stck_clpr': '10200'},
            {'stck_hgpr': '10600', 'stck_lwpr': '10100', 'stck_clpr': '10300'},
            {'stck_hgpr': '10300', 'stck_lwpr': '9800', 'stck_clpr': '10000'},
            {'stck_hgpr': '10800', 'stck_lwpr': '10300', 'stck_clpr': '10500'},
            {'stck_hgpr': '10900', 'stck_lwpr': '10400', 'stck_clpr': '10600'},
            {'stck_hgpr': '11500', 'stck_lwpr': '10800', 'stck_clpr': '11200'},
            {'stck_hgpr': '11100', 'stck_lwpr': '10600', 'stck_clpr': '10800'},
            {'stck_hgpr': '11200', 'stck_lwpr': '10700', 'stck_clpr': '10900'},
            {'stck_hgpr': '11800', 'stck_lwpr': '11200', 'stck_clpr': '11500'},
            {'stck_hgpr': '11400', 'stck_lwpr': '10900', 'stck_clpr': '11100'},
            {'stck_hgpr': '11500', 'stck_lwpr': '11000', 'stck_clpr': '11200'},
            {'stck_hgpr': '12000', 'stck_lwpr': '11500', 'stck_clpr': '11800'},
            {'stck_hgpr': '11700', 'stck_lwpr': '11200', 'stck_clpr': '11400'},
            {'stck_hgpr': '11800', 'stck_lwpr': '11300', 'stck_clpr': '11500'},
            {'stck_hgpr': '11900', 'stck_lwpr': '11400', 'stck_clpr': '11600'},
        ]

    def test_calculate_atr_with_adjust_true(self):
        """
        Tests that the calculate_atr function now uses adjust=True and thus produces
        the correct, adjusted ATR value.
        """
        # Calculate the ATR using the (now fixed) function
        atr_from_function = calculate_atr(self.daily_price_history, period=14)

        # Manually calculate the *correct* ATR with adjust=True
        df = pd.DataFrame(self.daily_price_history)
        df['high'] = df['stck_hgpr'].astype(float)
        df['low'] = df['stck_lwpr'].astype(float)
        df['close'] = df['stck_clpr'].astype(float)
        df['tr1'] = abs(df['high'] - df['low'])
        df['tr2'] = abs(df['high'] - df['close'].shift(1))
        df['tr3'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        correct_atr = df['tr'].ewm(alpha=1/14, adjust=True).mean().iloc[-1]

        # Manually calculate the *incorrect* ATR with adjust=False
        incorrect_atr = df['tr'].ewm(alpha=1/14, adjust=False).mean().iloc[-1]

        # Assert that the function's output is now the correct, adjusted value
        self.assertEqual(atr_from_function, correct_atr)

        # Assert that the function's output is no longer the incorrect, unadjusted value
        self.assertNotEqual(atr_from_function, incorrect_atr)


from .filters import determine_market_mode

class MarketModeTest(TestCase):
    def test_determine_market_mode(self):
        """
        Tests that determine_market_mode works correctly.
        """
        # 1. Simulate KOSPI data where the close is below the 60-day MA
        history_dca = []
        for i in range(70):
            price = 100 - i
            history_dca.append({'stck_clpr': str(price)})

        # 2. Simulate KOSPI data where the close is above the 60-day MA
        history_trading = []
        for i in range(70):
            price = 50 + i
            history_trading.append({'stck_clpr': str(price)})

        # 3. Call the function with both datasets
        mode_dca = determine_market_mode(history_dca)
        mode_trading = determine_market_mode(history_trading)

        # 4. Assert the correct modes are returned
        self.assertEqual(mode_dca, '우량주 분할매수 모드')
        self.assertEqual(mode_trading, '단기 트레이딩 모드')