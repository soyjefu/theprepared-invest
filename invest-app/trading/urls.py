# invest-app/trading/urls.py
from django.urls import path
from . import views

app_name = 'trading'

urlpatterns = [
    path('', views.root_redirect, name='root_redirect'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('analysis/run/', views.trigger_stock_analysis, name='run_analysis'),
    path('analysis/status/', views.get_analysis_status, name='get_analysis_status'),
    path('investment_strategy/', views.investment_strategy, name='investment_strategy'),

    # API for updating task schedules
    path('api/task/update/', views.update_task_schedule, name='update_task_schedule'),
]