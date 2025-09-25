from django.test import TestCase
from django.contrib.auth.models import User
from trading.models import TradingAccount, Portfolio, TradeLog
from django.db.utils import IntegrityError

class PortfolioModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('testuser', 'password')
        self.account = TradingAccount.objects.create(
            user=self.user,
            account_name='Test Account',
            account_number='12345',
            brokerage='Test Brokerage',
            app_key='test_key',
            app_secret='test_secret'
        )

    def test_can_reopen_closed_position(self):
        """
        Tests that a new position can be opened for a stock that was previously closed.
        """
        # Create and close a position
        Portfolio.objects.create(
            account=self.account,
            symbol='AAPL',
            stock_name='Apple Inc.',
            quantity=10,
            average_buy_price=150.00,
            stop_loss_price=140.00,
            target_price=160.00,
            is_open=False  # Mark as closed
        )

        # Attempt to create a new, open position for the same stock
        try:
            new_position = Portfolio.objects.create(
                account=self.account,
                symbol='AAPL',
                stock_name='Apple Inc.',
                quantity=5,
                average_buy_price=155.00,
                stop_loss_price=145.00,
                target_price=165.00,
                is_open=True
            )
            self.assertIsNotNone(new_position.pk, "Should be able to create a new open position for a previously closed stock.")
        except IntegrityError:
            self.fail("Should not raise an IntegrityError when creating a new open position for a previously closed stock.")