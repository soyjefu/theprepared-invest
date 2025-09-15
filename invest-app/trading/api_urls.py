from django.urls import path
from . import api_views

app_name = 'trading_api'

urlpatterns = [
    path('portfolio/<int:pk>/', api_views.PortfolioDetailAPIView.as_view(), name='portfolio-detail'),
    path('accounts/<int:account_id>/liquidate/', api_views.LiquidateAPIView.as_view(), name='account-liquidate'),
    path('ai/recommendations/', api_views.AIRecommendationAPIView.as_view(), name='ai-recommendations'),
]
