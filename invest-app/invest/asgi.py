# invest-app/invest/asgi.py
"""
ASGI config for invest project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import trading.routing

# 올바른 환경 변수 키 사용
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'invest.settings')
# Explicitly setup Django to avoid AppRegistryNotReady error.
django.setup()

# HTTP와 WebSocket 프로토콜을 분기
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            trading.routing.websocket_urlpatterns
        )
    ),
})