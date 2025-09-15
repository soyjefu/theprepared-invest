# invest-app/trading/urls.py
from django.urls import path, include
from . import views

app_name = 'trading'

urlpatterns = [
    path('', views.root_redirect, name='root_redirect'),

    # Page URLs
    path('dashboard/', views.dashboard, name='dashboard'),
    path('portfolio/', views.portfolio, name='portfolio'),
    path('orders/', views.orders, name='orders'),
    path('system/', views.system_management, name='system_management'),

    # Utility URLs
    path('analysis/run/', views.trigger_stock_analysis, name='run_analysis'),
    path('analysis/status/', views.get_analysis_status, name='get_analysis_status'),

    # API URLs
    path('api/', include('trading.api_urls', namespace='trading_api')),
    path('api/task/update/', views.update_task_schedule, name='update_task_schedule'),
]