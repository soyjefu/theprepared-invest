from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import StrategySettings, Portfolio, TradeLog, AnalyzedStock, TradingAccount
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from .kis_client import KISApiClient
from .tasks import analyze_stocks_task
from decimal import Decimal
import logging
import json
from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.urls import reverse

logger = logging.getLogger(__name__)

def root_redirect(request):
    """
    Redirects the root URL ('/') to the main dashboard ('/dashboard/').
    """
    return HttpResponseRedirect(reverse('trading:dashboard'))

# --- Page Views ---

@login_required
def dashboard(request):
    """
    Displays the main dashboard, showing a summary of all active accounts.
    It fetches live data for the balance summary but uses the local Portfolio
    database for position details to ensure all necessary data is available.
    """
    context = {}
    all_accounts = TradingAccount.objects.filter(user=request.user, is_active=True)
    account_details = []
    grand_total_assets = Decimal('0.0')

    for account in all_accounts:
        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_no=account.account_number,
            account_type=account.account_type
        )

        # Fetch live balance summary
        balance_summary = None
        error_msg = None
        try:
            balance_res = client.get_account_balance()
            if balance_res and balance_res.is_ok():
                body = balance_res.get_body()
                balance_summary_list = body.get('output2', [])
                if balance_summary_list:
                    balance_summary = balance_summary_list[0]
                    grand_total_assets += Decimal(balance_summary.get('tot_evlu_amt', '0'))
            else:
                error_msg = f"API Error: {balance_res.get_error_message() if balance_res else 'No response'}"
        except Exception as e:
            logger.error(f"Error fetching balance for account {account.account_name}: {e}", exc_info=True)
            error_msg = f"Application Error: {e}"

        # Fetch positions from our database and enrich with live data
        positions_from_db = list(Portfolio.objects.filter(account=account, is_open=True))
        for pos in positions_from_db:
            try:
                price_res = client.get_current_price(pos.symbol)
                if price_res and price_res.is_ok():
                    current_price = Decimal(price_res.get_body().get('output', {}).get('stck_prpr', '0'))
                    pos.current_price = current_price
                    pos.evlu_amt = pos.quantity * current_price
                    if pos.average_buy_price > 0:
                        pos.evlu_pfls_rt = ((current_price / pos.average_buy_price) - 1) * 100
                    else:
                        pos.evlu_pfls_rt = 0
                else:
                    pos.current_price = pos.average_buy_price # Fallback
                    pos.evlu_amt = pos.quantity * pos.average_buy_price
                    pos.evlu_pfls_rt = 0
            except Exception as e:
                logger.error(f"Error fetching current price for {pos.symbol}: {e}")
                pos.current_price = pos.average_buy_price
                pos.evlu_amt = pos.quantity * pos.average_buy_price
                pos.evlu_pfls_rt = 0

        account_details.append({
            'account': account,
            'balance_summary': balance_summary,
            'positions': positions_from_db, # Use our enriched model data
            'error': error_msg
        })

    context['account_details'] = account_details
    context['grand_total_assets'] = grand_total_assets
    return render(request, 'trading/dashboard.html', context)

@login_required
def portfolio(request):
    """
    Displays the detailed portfolio management page.
    """
    portfolio_items = Portfolio.objects.filter(account__user=request.user, is_open=True).order_by('stock_name')
    context = {
        'portfolio_items': portfolio_items
    }
    return render(request, 'trading/portfolio.html', context)

@login_required
def orders(request):
    """
    Displays the order and trade history page.
    """
    trade_logs = TradeLog.objects.filter(account__user=request.user).order_by('-timestamp')[:100] # Limit to recent 100
    context = {
        'trade_logs': trade_logs
    }
    return render(request, 'trading/orders.html', context)

@login_required
def system_management(request):
    """
    Displays the page for managing system settings, AI analysis, and periodic tasks.
    """
    context = {
        'settings': StrategySettings.objects.first(),
        'analyzed_stocks': AnalyzedStock.objects.filter(is_investable=True).order_by('-analysis_date')[:20],
        'periodic_tasks': PeriodicTask.objects.select_related('crontab', 'interval').all()
    }
    return render(request, 'trading/system_management.html', context)


# --- Utility & API Views (kept from original) ---

@login_required
def trigger_stock_analysis(request):
    """
    Triggers the Celery task to run the stock analysis.
    """
    if request.method == 'POST':
        analyze_stocks_task.delay()
        messages.success(request, "수동 주식 분석 작업이 시작되었습니다. 잠시 후 결과가 반영됩니다.")
    return redirect('trading:system_management') # Redirect back to the management page

def get_analysis_status(request):
    """
    Gets the status of the running analysis task from the cache.
    """
    progress_data = cache.get('analysis_progress')
    if progress_data:
        return JsonResponse(progress_data)
    return JsonResponse({'status': 'idle', 'progress': 0})

@login_required
@require_POST
def update_task_schedule(request):
    """
    API endpoint to update a periodic task's schedule and status.
    """
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        new_crontab_str = data.get('schedule')
        is_enabled = data.get('enabled')

        if not all([task_id, new_crontab_str, is_enabled is not None]):
            return JsonResponse({'status': 'error', 'message': 'Missing required parameters.'}, status=400)

        task = PeriodicTask.objects.get(id=task_id)
        task.enabled = is_enabled

        if task.crontab:
            current_crontab_str = f"{task.crontab.minute} {task.crontab.hour} {task.crontab.day_of_month} {task.crontab.month_of_year} {task.crontab.day_of_week}"
            if new_crontab_str != current_crontab_str:
                minute, hour, day_of_month, month_of_year, day_of_week = new_crontab_str.split()
                crontab_schedule, _ = CrontabSchedule.objects.get_or_create(
                    minute=minute, hour=hour, day_of_month=day_of_month,
                    month_of_year=month_of_year, day_of_week=day_of_week
                )
                task.crontab = crontab_schedule

        task.save()
        return JsonResponse({'status': 'success', 'message': 'Task updated successfully.'})

    except PeriodicTask.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Task not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error updating task schedule: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# The 'investment_strategy' view was very specific and seems to be replaced by the new structure.
# I am removing it for now to simplify. If it's needed, it can be re-integrated.