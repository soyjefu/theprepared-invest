# invest-app/trading/models.py
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User

class TradingAccount(models.Model):
    """
    Represents a user's brokerage account credentials and settings.

    This model stores the necessary information to connect to a brokerage API,
    including API keys and account details. It links a brokerage account to a
    user in the system.
    """
    class AccountType(models.TextChoices):
        SIMULATED = 'SIM', 'Simulated'
        REAL = 'REAL', 'Real'

    user = models.ForeignKey(User, on_delete=models.CASCADE, help_text="The user associated with this account.")
    account_name = models.CharField(max_length=100, help_text="A nickname for the account.")
    account_number = models.CharField(max_length=20, unique=True, help_text="The brokerage account number.")
    account_type = models.CharField(max_length=4, choices=AccountType.choices, default=AccountType.SIMULATED, help_text="The type of account (Simulated/Real).")
    brokerage = models.CharField(max_length=50, default="Korea Investment & Securities", help_text="The name of the brokerage.")
    app_key = models.CharField(max_length=255, help_text="API Key for the brokerage.")
    app_secret = models.CharField(max_length=255, help_text="API Secret for the brokerage.")
    is_active = models.BooleanField(default=True, help_text="Whether the account is currently active for trading.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.account_name} ({self.get_account_type_display()})"

class TradeLog(models.Model):
    """
    Records every trade attempt, whether successful, pending, or failed.

    This model acts as an immutable log of all order-related activities,
    providing a history for auditing and debugging purposes.
    """
    class TradeType(models.TextChoices):
        BUY = 'BUY', 'Buy'
        SELL = 'SELL', 'Sell'

    class TradeStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        EXECUTED = 'EXECUTED', 'Executed'
        FAILED = 'FAILED', 'Failed'
        CANCELED = 'CANCELED', 'Canceled'

    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='trade_logs')
    symbol = models.CharField(max_length=20, help_text="The stock symbol (ticker).")
    order_id = models.CharField(max_length=100, help_text="The order ID from the brokerage.")
    trade_type = models.CharField(max_length=4, choices=TradeType.choices, help_text="The type of trade (Buy/Sell).")
    quantity = models.PositiveIntegerField(help_text="The number of shares.")
    price = models.DecimalField(max_digits=15, decimal_places=2, help_text="The price per share.")
    status = models.CharField(max_length=10, choices=TradeStatus.choices, default=TradeStatus.PENDING, help_text="The current status of the trade.")
    timestamp = models.DateTimeField(auto_now_add=True)
    log_message = models.TextField(blank=True, help_text="Detailed message or error log for the trade.")

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.account.account_name} - {self.symbol} {self.get_trade_type_display()} ({self.status})"

class AnalyzedStock(models.Model):
    """
    Stores the results of the AI stock analysis.

    This model holds information about stocks that have been screened and
    analyzed, including their investability, recommended investment horizon,
    and the raw data used for the analysis.
    """
    class Horizon(models.TextChoices):
        SHORT = 'SHORT', 'Short-term'
        MID = 'MID', 'Mid-term'
        LONG = 'LONG', 'Long-term'
        NONE = 'NONE', 'Unclassified'

    symbol = models.CharField(max_length=20, unique=True, help_text="The stock symbol (ticker).")
    stock_name = models.CharField(max_length=100, help_text="The name of the stock.")
    is_investable = models.BooleanField(default=False, help_text="Whether the stock passed the initial screening.")
    investment_horizon = models.CharField(
        max_length=5, choices=Horizon.choices, default=Horizon.NONE,
        help_text="The recommended investment horizon from the AI analysis."
    )
    analysis_date = models.DateField(auto_now=True, help_text="The date the analysis was performed.")
    last_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="The stock price at the time of analysis.")
    raw_analysis_data = models.JSONField(default=dict, blank=True, help_text="Raw data used in the analysis (e.g., financial ratios).")

    def __str__(self):
        return f"[{self.symbol}] {self.stock_name} ({self.get_investment_horizon_display()})"

class Portfolio(models.Model):
    """
    Represents a single, open position in a user's portfolio.

    This model tracks the state of a currently held stock, including the
    quantity, average buy price, and the risk management criteria (stop-loss
    and target prices).
    """
    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='portfolio_items')
    symbol = models.CharField(max_length=20, help_text="The stock symbol (ticker).")
    stock_name = models.CharField(max_length=100, help_text="The name of the stock.")
    quantity = models.PositiveIntegerField(help_text="The number of shares held.")
    average_buy_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="The average price at which the shares were bought.")
    
    stop_loss_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="The price at which to trigger a stop-loss sale.")
    target_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="The price at which to trigger a take-profit sale.")

    is_open = models.BooleanField(default=True, help_text="Whether this is an open position.")
    entry_log = models.ForeignKey(TradeLog, on_delete=models.SET_NULL, null=True, related_name='portfolio_entry', help_text="The trade log entry for the purchase of this position.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'symbol'],
                condition=models.Q(is_open=True),
                name='unique_open_position_per_account'
            )
        ]

    def __str__(self):
        status = "OPEN" if self.is_open else "CLOSED"
        return f"[{self.account.account_name}] {self.symbol}: {self.quantity} shares @{self.average_buy_price} ({status})"


from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator

class StrategySettings(models.Model):
    """
    A singleton model to manage global settings for the AI trading strategy.

    This model ensures that there is only one set of strategy settings for
    the entire application. It defines the capital allocation percentages for
    different investment horizons.
    """
    short_term_allocation = models.DecimalField(
        max_digits=5, decimal_places=2, default=30.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of capital to allocate to the short-term strategy."
    )
    mid_term_allocation = models.DecimalField(
        max_digits=5, decimal_places=2, default=40.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of capital to allocate to the mid-term strategy."
    )
    long_term_allocation = models.DecimalField(
        max_digits=5, decimal_places=2, default=30.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of capital to allocate to the long-term strategy."
    )
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Validates that the sum of all allocations is exactly 100%."""
        total_allocation = self.short_term_allocation + self.mid_term_allocation + self.long_term_allocation
        if total_allocation != 100:
            raise ValidationError(f"The sum of all allocations must be 100%. Current sum: {total_allocation}%.")

    def save(self, *args, **kwargs):
        """
        Overrides the save method to enforce a singleton pattern.

        This ensures that only one instance of StrategySettings can ever be
        created in the database.
        """
        if not self.pk and StrategySettings.objects.exists():
            raise ValidationError("Only one instance of StrategySettings is allowed. Please edit the existing one.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (f"Strategy Allocations (Short: {self.short_term_allocation}%, "
                f"Mid: {self.mid_term_allocation}%, Long: {self.long_term_allocation}%)")

    class Meta:
        verbose_name = "AI Strategy Settings"
        verbose_name_plural = "AI Strategy Settings"


class HistoricalPriceData(models.Model):
    """
    Stores historical daily price data for each stock.
    Used for backtesting and technical analysis calculations.
    """
    symbol = models.CharField(max_length=20, db_index=True, help_text="The stock symbol (ticker).")
    date = models.DateField(db_index=True, help_text="The date of the price data.")
    open_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="Opening price.")
    high_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="Highest price of the day.")
    low_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="Lowest price of the day.")
    close_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="Closing price.")
    volume = models.BigIntegerField(help_text="Trading volume for the day.")

    class Meta:
        unique_together = ('symbol', 'date')
        ordering = ['-date']
        verbose_name = "Historical Price Data"
        verbose_name_plural = "Historical Price Data"

    def __str__(self):
        return f"{self.symbol} on {self.date}: {self.close_price}"