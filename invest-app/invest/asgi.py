# invest-app/invest/asgi.py
"""
ASGI config for invest project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# 올바른 환경 변수 키 사용
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'invest.settings')

# HTTP 프로토콜용 ASGI 애플리케이션을 먼저 로드하여 Django 초기화
django_asgi_app = get_asgi_application()

import trading.routing

# HTTP와 WebSocket 프로토콜을 분기
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            trading.routing.websocket_urlpatterns
        )
    ),
})