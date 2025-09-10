# invest-app/trading/routing.py

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/trade/(?P<account_id>\w+)/$', consumers.TradeConsumer.as_asgi()),
]