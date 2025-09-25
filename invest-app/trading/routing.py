# invest-app/trading/routing.py

from django.urls import re_path
from . import consumers

# Defines the WebSocket URL patterns for the application.
websocket_urlpatterns = [
    # Route for the main dashboard WebSocket connection.
    # It captures the 'account_id' to associate the connection with a specific trading account.
    re_path(r'ws/trade/(?P<account_id>\w+)/$', consumers.DashboardConsumer.as_asgi()),
]