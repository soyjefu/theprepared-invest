# invest-app/trading/urls.py
from django.urls import path
from . import views

app_name = 'trading'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('analysis/run/', views.trigger_stock_analysis, name='run_analysis'),
]