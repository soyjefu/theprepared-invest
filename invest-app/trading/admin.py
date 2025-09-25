# invest-app/trading/admin.py
from django.contrib import admin
from .models import TradingAccount, TradeLog, StrategySettings, AnalyzedStock, Portfolio

@admin.register(AnalyzedStock)
class AnalyzedStockAdmin(admin.ModelAdmin):
    """
    Admin interface customization for the AnalyzedStock model.
    """
    list_display = ('analysis_date', 'symbol', 'stock_name', 'investment_horizon', 'is_investable', 'formatted_last_price')
    list_filter = ('investment_horizon', 'is_investable', 'analysis_date')
    search_fields = ('symbol', 'stock_name')
    ordering = ('-analysis_date',)

    def formatted_last_price(self, obj):
        """Formats the last price with commas for readability."""
        if obj.last_price is None:
            return "—"
        return f"{int(obj.last_price):,}"
    formatted_last_price.short_description = 'Last Price'
    formatted_last_price.admin_order_field = 'last_price'

@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    """
    Admin interface customization for the Portfolio model.
    """
    list_display = ('account', 'symbol', 'stock_name', 'quantity', 'formatted_average_buy_price', 'is_open', 'updated_at')
    list_filter = ('is_open', 'account')
    search_fields = ('symbol', 'stock_name')
    ordering = ('-updated_at',)

    def formatted_average_buy_price(self, obj):
        """Formats the average buy price with commas for readability."""
        if obj.average_buy_price is None:
            return "—"
        return f"{int(obj.average_buy_price):,}"
    formatted_average_buy_price.short_description = 'Average Buy Price'
    formatted_average_buy_price.admin_order_field = 'average_buy_price'


@admin.register(StrategySettings)
class StrategySettingsAdmin(admin.ModelAdmin):
    """
    Admin interface customization for the singleton StrategySettings model.
    """
    list_display = ('short_term_allocation', 'mid_term_allocation', 'long_term_allocation', 'updated_at')

    def has_add_permission(self, request):
        """Prevents adding new settings if one already exists."""
        return not StrategySettings.objects.exists()

@admin.register(TradingAccount)
class TradingAccountAdmin(admin.ModelAdmin):
    """
    Admin interface customization for the TradingAccount model.
    """
    list_display = ('user', 'account_name', 'account_number', 'brokerage', 'account_type', 'is_active')
    list_filter = ('brokerage', 'account_type', 'is_active')
    search_fields = ('user__username', 'account_name', 'account_number')

@admin.register(TradeLog)
class TradeLogAdmin(admin.ModelAdmin):
    """
    Admin interface customization for the TradeLog model.
    """
    list_display = ('timestamp', 'account', 'symbol', 'trade_type', 'status', 'quantity', 'formatted_price')
    list_filter = ('status', 'trade_type', 'account')
    search_fields = ('symbol', 'order_id')
    ordering = ('-timestamp',)

    def formatted_price(self, obj):
        """Formats the price with commas for readability."""
        if obj.price is None:
            return "—"
        return f"{int(obj.price):,}"
    formatted_price.short_description = 'Price'
    formatted_price.admin_order_field = 'price'