from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import StrategySettings, Portfolio, TradeLog, AnalyzedStock, TradingAccount
from .kis_client import KISApiClient
from .tasks import analyze_stocks_task
from decimal import Decimal
import logging
from django.http import JsonResponse, HttpResponseRedirect
from django.core.cache import cache
from django.urls import reverse

logger = logging.getLogger(__name__)

def root_redirect(request):
    """
    Redirects the root URL ('/') to the main dashboard ('/dashboard/').
    """
    return HttpResponseRedirect(reverse('trading:dashboard'))

@login_required
def dashboard(request):
    """
    Displays the main monitoring dashboard for the trading application.
    Shows a consolidated view of all active accounts.
    """
    context = {}
    all_accounts = TradingAccount.objects.filter(user=request.user, is_active=True)

    account_details = []
    grand_total_assets = Decimal('0.0')

    for account in all_accounts:
        detail = {
            'account': account,
            'balance_summary': None,
            'positions': [],
            'error': None
        }
        try:
            client = KISApiClient(
                app_key=account.app_key,
                app_secret=account.app_secret,
                account_no=account.account_number,
                account_type=account.account_type
            )
            balance_res = client.get_account_balance()

            if balance_res and balance_res.is_ok():
                body = balance_res.get_body()

                # Correctly parse balance summary from output2
                balance_summary_list = body.get('output2', [])
                if balance_summary_list:
                    summary = balance_summary_list[0]
                    detail['balance_summary'] = summary
                    grand_total_assets += Decimal(summary.get('tot_evlu_amt', '0'))

                # Get positions from output1
                detail['positions'] = body.get('output1', [])
            else:
                error_msg = balance_res.get_error_message() if balance_res else "No response from API."
                detail['error'] = f"API Error: {error_msg}"
        except Exception as e:
            logger.error(f"Error fetching balance for account {account.account_name}: {e}", exc_info=True)
            detail['error'] = f"Application Error: {e}"

        account_details.append(detail)

    context['account_details'] = account_details
    context['grand_total_assets'] = grand_total_assets

    # Get strategy settings
    context['settings'] = StrategySettings.objects.first()

    # Get all analyzed stocks for display
    context['analyzed_stocks'] = AnalyzedStock.objects.filter(is_investable=True).order_by('-analysis_date')[:20]

    # Get recent trade logs for all accounts
    context['recent_trades'] = TradeLog.objects.filter(account__in=all_accounts).order_by('-timestamp')[:20]

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

def get_analysis_status(request):
    """
    Gets the status of the running analysis task from the cache.
    """
    progress_data = cache.get('analysis_progress')
    if progress_data:
        return JsonResponse(progress_data)
    return JsonResponse({'status': 'idle', 'progress': 0})

import json
from .analysis.market_scanner import screen_initial_stocks
from .ai_analysis_service import get_detailed_strategy
from dataclasses import asdict

@login_required
def investment_strategy(request):
    """
    Handles the multi-step, interactive investment strategy analysis.
    - GET: Renders the main page.
    - POST with action 'screen_stocks': Runs the initial screening and returns a list of stocks.
    - POST with action 'get_strategy': Returns a detailed investment strategy for a given stock.
    """
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        action = request.GET.get('action')

        if action == 'screen_stocks':
            try:
                screen_initial_stocks()
                investable_stocks = AnalyzedStock.objects.filter(is_investable=True).order_by('stock_name')

                stock_list = list(investable_stocks.values('stock_name', 'symbol', 'last_price'))

                return JsonResponse({'status': 'success', 'stocks': stock_list})
            except Exception as e:
                logger.error(f"Error during stock screening: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        elif action == 'get_strategy':
            try:
                data = json.loads(request.body)
                symbol = data.get('symbol')
                horizon = data.get('horizon')

                if not symbol or not horizon:
                    return JsonResponse({'status': 'error', 'message': 'Symbol and horizon are required.'}, status=400)

                strategy_result = get_detailed_strategy(request.user, symbol, horizon)

                if strategy_result:
                    return JsonResponse({'status': 'success', 'strategy': asdict(strategy_result)})
                else:
                    return JsonResponse({'status': 'error', 'message': 'Failed to generate strategy.'}, status=500)

            except Exception as e:
                logger.error(f"Error getting strategy: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)

    # For standard GET requests, just render the page template.
    context = {}
    return render(request, 'trading/investment_strategy.html', context)