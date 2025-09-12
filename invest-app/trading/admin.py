# invest-app/trading/admin.py
from django.contrib import admin
from .models import TradingAccount, TradeLog, StrategySettings, AnalyzedStock, Portfolio

# 수정: 새로운 모델들을 admin 사이트에 등록합니다.
@admin.register(AnalyzedStock)
class AnalyzedStockAdmin(admin.ModelAdmin):
    list_display = ('analysis_date', 'symbol', 'stock_name', 'investment_horizon', 'is_investable', 'last_price')
    list_filter = ('investment_horizon', 'is_investable', 'analysis_date')
    search_fields = ('symbol', 'stock_name')
    ordering = ('-analysis_date',)

@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ('account', 'symbol', 'stock_name', 'quantity', 'average_buy_price', 'is_open', 'updated_at')
    list_filter = ('is_open', 'account')
    search_fields = ('symbol', 'stock_name')
    ordering = ('-updated_at',)


@admin.register(StrategySettings)
class StrategySettingsAdmin(admin.ModelAdmin):
    list_display = ('short_term_allocation', 'mid_term_allocation', 'long_term_allocation', 'updated_at')

    def has_add_permission(self, request):
        # Allow adding if no settings exist yet
        return not StrategySettings.objects.exists()

@admin.register(TradingAccount)
class TradingAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'account_name', 'account_number', 'brokerage', 'account_type', 'is_active')
    list_filter = ('brokerage', 'account_type', 'is_active')
    search_fields = ('user__username', 'account_name', 'account_number')

@admin.register(TradeLog)
class TradeLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'account', 'symbol', 'trade_type', 'status', 'quantity', 'price')
    list_filter = ('status', 'trade_type', 'account')
    search_fields = ('symbol', 'order_id')
    ordering = ('-timestamp',)