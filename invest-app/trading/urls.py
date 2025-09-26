# invest-app/trading/urls.py
from django.urls import path, include
from . import views

app_name = 'trading'

urlpatterns = [
    # Root redirect
    path('', views.root_redirect, name='root_redirect'),

    # Main page views
    path('dashboard/', views.dashboard, name='dashboard'),
    path('portfolio/', views.portfolio, name='portfolio'),
    path('orders/', views.orders, name='orders'),
    path('settings/', views.strategy_settings_view, name='strategy_settings'),
    path('system/', views.system_management, name='system_management'),

    # Endpoint to trigger Celery tasks
    path('screening/run/', views.trigger_stock_screening, name='run_screening'),

    # API endpoints
    path('api/', include('trading.api_urls', namespace='trading_api')),
    path('api/task/update/', views.update_task_schedule, name='update_task_schedule'),
]