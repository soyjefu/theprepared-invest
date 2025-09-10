# invest-app/trading/admin.py
from django.contrib import admin
from .models import TradingAccount, Strategy, AccountStrategy, TradeLog

# 수정: 새로운 모델들을 admin 사이트에 등록합니다.
@admin.register(TradingAccount)
class TradingAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'account_name', 'account_number', 'brokerage', 'account_type', 'is_active')
    list_filter = ('brokerage', 'account_type', 'is_active')
    search_fields = ('user__username', 'account_name', 'account_number')

@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

@admin.register(AccountStrategy)
class AccountStrategyAdmin(admin.ModelAdmin):
    list_display = ('account', 'strategy', 'is_active', 'trading_capital')
    list_filter = ('is_active',)
    search_fields = ('account__account_name', 'strategy__name')

@admin.register(TradeLog)
class TradeLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'account', 'symbol', 'trade_type', 'status', 'quantity', 'price')
    list_filter = ('status', 'trade_type', 'account')
    search_fields = ('symbol', 'order_id')
    ordering = ('-timestamp',)