from django.urls import path
from . import views

app_name = 'strategy_engine'

urlpatterns = [
    path('backtest/', views.backtest_view, name='backtest'),
]