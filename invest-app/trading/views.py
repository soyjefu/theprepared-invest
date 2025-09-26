from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import StrategySettings, Portfolio, TradeLog, AnalyzedStock, TradingAccount
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from .kis_client import KISApiClient
from .tasks import run_stock_screening_task
from decimal import Decimal
import logging
import json
from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.urls import reverse
from .forms import StrategySettingsForm

logger = logging.getLogger(__name__)

@login_required
def strategy_settings_view(request):
    """
    View to manage the singleton StrategySettings model.
    """
    settings = StrategySettings.get_solo()
    if request.method == 'POST':
        form = StrategySettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Strategy settings have been updated successfully.')
            return redirect('trading:strategy_settings')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StrategySettingsForm(instance=settings)

    context = {
        'form': form,
        'page_title': 'Strategy Settings'
    }
    return render(request, 'trading/settings.html', context)


def root_redirect(request):
    """
    Redirects the root URL ('/') to the main dashboard.

    Args:
        request: The HttpRequest object.

    Returns:
        An HttpResponseRedirect to the dashboard URL.
    """
    return HttpResponseRedirect(reverse('trading:dashboard'))

# --- Page Views ---

from .trading_service import DailyTrader

@login_required
def dashboard(request):
    """
    Renders the main dashboard page.

    This view fetches and displays a summary of all active trading accounts
    for the logged-in user. It retrieves live balance information from the API
    and combines it with portfolio data from the local database.

    Args:
        request: The HttpRequest object.

    Returns:
        An HttpResponse object rendering the dashboard template with context.
        The context includes:
        - 'account_details': A list of dictionaries, each containing account
          info, balance, positions, and any errors.
        - 'grand_total_assets': The sum of assets across all accounts.
    """
    context = {}
    all_accounts = TradingAccount.objects.filter(user=request.user, is_active=True)
    account_details = []
    grand_total_assets = Decimal('0.0')
    market_mode = "Unknown" # Default

    if all_accounts.exists():
        # 첫 번째 계정 기준으로 시장 모드 판단 (어차피 시장은 하나이므로)
        try:
            # DailyTrader를 생성하되, 실제 거래는 하지 않으므로 user만 넘겨 초기화
            trader = DailyTrader(user=request.user, account_number=all_accounts.first().account_number)
            market_mode, _ = trader.get_market_mode()
        except Exception as e:
            logger.error(f"Failed to determine market mode for dashboard: {e}")
            market_mode = "Error"

    for account in all_accounts:
        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_no=account.account_number,
            account_type=account.account_type
        )

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
                    pos.current_price = pos.average_buy_price
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
            'positions': positions_from_db,
            'error': error_msg
        })

    context['account_details'] = account_details
    context['grand_total_assets'] = grand_total_assets
    context['market_mode'] = market_mode
    return render(request, 'trading/dashboard.html', context)

@login_required
def portfolio(request):
    """
    Renders the portfolio management page.

    Args:
        request: The HttpRequest object.

    Returns:
        An HttpResponse object rendering the portfolio template with context.
        The context includes:
        - 'portfolio_items': A queryset of all open portfolio items for the user.
    """
    portfolio_items = Portfolio.objects.filter(account__user=request.user, is_open=True).order_by('stock_name')
    context = {
        'portfolio_items': portfolio_items
    }
    return render(request, 'trading/portfolio.html', context)

@login_required
def orders(request):
    """
    Renders the order and trade history page.

    Args:
        request: The HttpRequest object.

    Returns:
        An HttpResponse object rendering the orders template with context.
        The context includes:
        - 'trade_logs': A queryset of the 100 most recent trade logs for the user.
    """
    trade_logs = TradeLog.objects.filter(account__user=request.user).order_by('-timestamp')[:100]
    context = {
        'trade_logs': trade_logs
    }
    return render(request, 'trading/orders.html', context)

@login_required
def system_management(request):
    """
    Renders the system management page.

    This page provides tools for managing strategy settings, viewing AI-analyzed
    stocks, and controlling periodic background tasks.

    Args:
        request: The HttpRequest object.

    Returns:
        An HttpResponse object rendering the system management template with context.
        The context includes:
        - 'settings': The current strategy settings.
        - 'analyzed_stocks': A queryset of recent investable stocks.
        - 'periodic_tasks': A queryset of all scheduled Celery tasks.
    """
    context = {
        'settings': StrategySettings.objects.first(),
        'analyzed_stocks': AnalyzedStock.objects.filter(is_investable=True).order_by('-analysis_date')[:20],
        'periodic_tasks': PeriodicTask.objects.select_related('crontab', 'interval').all()
    }
    return render(request, 'trading/system_management.html', context)


# --- Utility & API Views (kept from original) ---

@login_required
@require_POST
def trigger_stock_screening(request):
    """
    Triggers the Celery task to run the stock screening and analysis.

    This is a POST-only view that initiates the `run_stock_screening_task`
    Celery task. It adds a success message and redirects the user back to the
    system management page.

    Args:
        request: The HttpRequest object.

    Returns:
        An HttpResponseRedirect to the system management page.
    """
    run_stock_screening_task.delay()
    messages.success(request, "종목 분석을 시작했습니다. 잠시 후 결과가 업데이트됩니다.")
    return redirect('trading:system_management')

@login_required
@require_POST
def update_task_schedule(request):
    """
    API endpoint to update a periodic task's schedule and status (enabled/disabled).

    Expects a JSON payload with 'task_id', 'schedule' (as a crontab string),
    and 'enabled' (boolean).

    Args:
        request: The HttpRequest object.

    Returns:
        A JsonResponse indicating success or failure.
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