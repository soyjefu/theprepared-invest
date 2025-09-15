from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from trading.models import TradingAccount, Portfolio, TradeLog, AnalyzedStock

class PortfolioSignalTest(TestCase):

    def setUp(self):
        """Set up the necessary objects for testing portfolio signals."""
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        self.account = TradingAccount.objects.create(
            user=self.user,
            account_name='Test Account',
            account_number='12345678-01',
            app_key='key',
            app_secret='secret'
        )
        self.analyzed_stock = AnalyzedStock.objects.create(
            symbol='005930',
            stock_name='Samsung Electronics',
            is_investable=True,
            raw_analysis_data={'stop_loss_price': 60000, 'target_price': 80000}
        )

    def test_portfolio_creation_on_first_buy(self):
        """Test that a new portfolio item is created after the first buy."""
        self.assertEqual(Portfolio.objects.count(), 0)

        # Simulate an executed buy trade
        TradeLog.objects.create(
            account=self.account,
            symbol='005930',
            trade_type='BUY',
            quantity=10,
            price=Decimal('70000'),
            status='EXECUTED'
        )

        self.assertEqual(Portfolio.objects.count(), 1)
        portfolio = Portfolio.objects.first()
        self.assertEqual(portfolio.symbol, '005930')
        self.assertEqual(portfolio.quantity, 10)
        self.assertEqual(portfolio.average_buy_price, Decimal('70000'))
        self.assertTrue(portfolio.is_open)

    def test_portfolio_update_on_second_buy(self):
        """Test that an existing portfolio is updated correctly on a second buy."""
        # Initial buy
        TradeLog.objects.create(
            account=self.account, symbol='005930', trade_type='BUY',
            quantity=10, price=Decimal('70000'), status='EXECUTED'
        )
        self.assertEqual(Portfolio.objects.count(), 1)

        # Second buy at a different price
        TradeLog.objects.create(
            account=self.account, symbol='005930', trade_type='BUY',
            quantity=5, price=Decimal('80000'), status='EXECUTED'
        )

        self.assertEqual(Portfolio.objects.count(), 1) # Should not create a new one
        portfolio = Portfolio.objects.first()
        self.assertEqual(portfolio.quantity, 15) # 10 + 5

        # Check average price calculation: (10*70000 + 5*80000) / 15 = 73333.33
        expected_avg_price = (Decimal('700000') + Decimal('400000')) / 15
        self.assertAlmostEqual(portfolio.average_buy_price, expected_avg_price, places=2)

    def test_portfolio_update_on_partial_sell(self):
        """Test that portfolio quantity is reduced on a partial sell."""
        # Initial buy
        TradeLog.objects.create(
            account=self.account, symbol='005930', trade_type='BUY',
            quantity=20, price=Decimal('75000'), status='EXECUTED'
        )

        # Partial sell
        TradeLog.objects.create(
            account=self.account, symbol='005930', trade_type='SELL',
            quantity=8, price=Decimal('80000'), status='EXECUTED'
        )

        portfolio = Portfolio.objects.first()
        self.assertEqual(portfolio.quantity, 12) # 20 - 8
        self.assertTrue(portfolio.is_open)

    def test_portfolio_closure_on_full_sell(self):
        """Test that a portfolio item is closed after selling all shares."""
        # Initial buy
        TradeLog.objects.create(
            account=self.account, symbol='005930', trade_type='BUY',
            quantity=15, price=Decimal('75000'), status='EXECUTED'
        )

        # Sell all shares
        TradeLog.objects.create(
            account=self.account, symbol='005930', trade_type='SELL',
            quantity=15, price=Decimal('80000'), status='EXECUTED'
        )

        portfolio = Portfolio.objects.first()
        self.assertEqual(portfolio.quantity, 0)
        self.assertFalse(portfolio.is_open)

from unittest.mock import patch, MagicMock
from trading.kis_client import KISApiClient

class OrderValidationTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('ordertester', 'order@test.com', 'password')
        self.account = TradingAccount.objects.create(
            user=self.user,
            account_name='Order Test Account',
            account_number='87654321-01',
            app_key='key',
            app_secret='secret'
        )
        self.client = KISApiClient(
            app_key=self.account.app_key,
            app_secret=self.account.app_secret,
            account_no=self.account.account_number
        )

    def test_duplicate_order_prevention(self):
        """Test that a duplicate pending order is prevented."""
        # Create a pending order
        TradeLog.objects.create(
            account=self.account,
            symbol='000660',
            trade_type='BUY',
            quantity=10,
            price=Decimal('100000'),
            status='PENDING'
        )

        # Mock the API call since we only want to test the validation
        with patch.object(self.client, '_send_request', return_value=None) as mock_send:
            response = self.client.place_order(
                account=self.account,
                symbol='000660',
                quantity=10,
                price=100000,
                order_type='BUY'
            )
            self.assertTrue(response.get('is_validation_error'))
            self.assertIn('Duplicate order', response.get('msg1'))
            mock_send.assert_not_called() # The API should not have been called

    @patch('trading.kis_client.KISApiClient.get_account_balance')
    def test_insufficient_funds_prevention(self, mock_get_balance):
        """Test that a buy order with insufficient funds is prevented."""
        # Simulate an API response showing only 50,000 KRW cash
        mock_response = MagicMock()
        mock_response.is_ok.return_value = True
        mock_response.get_body.return_value = {
            'output2': [{'dnca_tot_amt': '50000'}]
        }
        mock_get_balance.return_value = mock_response

        # Attempt to place an order worth 100,000 KRW
        response = self.client.place_order(
            account=self.account,
            symbol='000660',
            quantity=1,
            price=100000,
            order_type='BUY'
        )
        self.assertTrue(response.get('is_validation_error'))
        self.assertIn('Insufficient funds', response.get('msg1'))

    @patch('trading.kis_client.KISApiClient.get_account_balance')
    def test_insufficient_holdings_prevention(self, mock_get_balance):
        """Test that a sell order with insufficient holdings is prevented."""
        # Simulate an API response showing the user holds 5 shares of the stock
        mock_response = MagicMock()
        mock_response.is_ok.return_value = True
        mock_response.get_body.return_value = {
            'output1': [{'pdno': '005930', 'hldg_qty': '5'}],
            'output2': [{'dnca_tot_amt': '100000'}] # Dummy cash balance
        }
        mock_get_balance.return_value = mock_response

        # Attempt to sell 10 shares
        response = self.client.place_order(
            account=self.account,
            symbol='005930',
            quantity=10,
            price=70000,
            order_type='SELL'
        )
        self.assertTrue(response.get('is_validation_error'))
        self.assertIn('Insufficient holdings', response.get('msg1'))
