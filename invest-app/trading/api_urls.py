from django.urls import path
from . import api_views

app_name = 'trading_api'

urlpatterns = [
    # Endpoint to retrieve or update a specific portfolio item's risk settings (e.g., stop-loss).
    path('portfolio/<int:pk>/', api_views.PortfolioDetailAPIView.as_view(), name='portfolio-detail'),

    # Endpoint to trigger the liquidation of assets in a specific account to reach a target cash percentage.
    path('accounts/<int:account_id>/liquidate/', api_views.LiquidateAPIView.as_view(), name='account-liquidate'),

    # Endpoint to get the latest AI-driven market trend analysis and recommended capital allocations.
    path('ai/recommendations/', api_views.AIRecommendationAPIView.as_view(), name='ai-recommendations'),

    # Endpoint to sell a single portfolio position.
    path('portfolio/<int:pk>/sell/', api_views.SellPositionAPIView.as_view(), name='portfolio-sell'),
]
