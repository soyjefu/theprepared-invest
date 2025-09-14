from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import StrategySettings, Portfolio, TradeLog, AnalyzedStock, TradingAccount
from .kis_client import KISApiClient
from .tasks import analyze_stocks_task
from decimal import Decimal

@login_required
def dashboard(request):
    """
    Displays the main monitoring dashboard for the trading application.
    Supports switching between multiple accounts via a GET parameter.
    """
    context = {}

    # 1. Handle Account Selection
    all_accounts = TradingAccount.objects.filter(user=request.user, is_active=True)
    selected_account_id = request.GET.get('account_id')

    if selected_account_id:
        selected_account = all_accounts.filter(pk=selected_account_id).first()
    else:
        selected_account = all_accounts.first()

    context['all_accounts'] = all_accounts
    context['selected_account'] = selected_account

    # 2. Get Account Balance from API for the selected account
    if selected_account:
        client = KISApiClient(app_key=selected_account.app_key, app_secret=selected_account.app_secret, account_no=selected_account.account_number, account_type=selected_account.account_type)
        balance_info_res = client.get_account_balance()
        if balance_info_res and balance_info_res.is_ok():
            balance_info = balance_info_res.get_body()
            output1_list = balance_info.get('output1', [])
            if output1_list:
                context['balance'] = output1_list[0]
            else:
                context['balance'] = None
                context['balance_error'] = "API returned empty balance information."
        else:
            context['balance'] = None
            error_msg = balance_info_res.get_error_message() if balance_info_res else "No response from API."
            context['balance_error'] = f"Failed to fetch account balance: {error_msg}"
    else:
        context['balance'] = None

    # 3. Get strategy settings
    context['settings'] = StrategySettings.objects.first()

    # 4. Get open positions and calculate P/L for the selected account
    open_positions = Portfolio.objects.filter(is_open=True, account=selected_account) if selected_account else []

    analyzed_stocks = {stock.symbol: stock.last_price for stock in AnalyzedStock.objects.all()}
    positions_with_pl = []
    total_pl = Decimal('0.0')

    for pos in open_positions:
        current_price = analyzed_stocks.get(pos.symbol, pos.average_buy_price)
        market_value = pos.quantity * current_price
        cost_basis = pos.quantity * pos.average_buy_price
        pl = market_value - cost_basis
        pl_percent = (pl / cost_basis) * 100 if cost_basis > 0 else 0

        positions_with_pl.append({
            'position': pos,
            'current_price': current_price,
            'market_value': market_value,
            'pl': pl,
            'pl_percent': pl_percent,
        })
        total_pl += pl

    context['open_positions'] = positions_with_pl
    context['total_pl'] = total_pl

    # 5. Get recent trade logs for the selected account
    context['recent_trades'] = TradeLog.objects.filter(account=selected_account).order_by('-timestamp')[:20] if selected_account else []

    return render(request, 'trading/dashboard.html', context)

@login_required
def trigger_stock_analysis(request):
    """
    Triggers the Celery task to run the stock analysis.
    """
    if request.method == 'POST':
        # run_daily_morning_routine.delay()
        analyze_stocks_task.delay()
        messages.success(request, "수동 주식 분석 작업이 시작되었습니다. 잠시 후 결과가 대시보드에 반영됩니다.")
    return redirect('trading:dashboard')