# invest-app/invest/wsgi.py
"""
WSGI config for invest project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# 수정: 'autotrader.settings' -> 'invest.settings'로 변경
os.environ.setdefault('DJANGO_SETTINGS_MODULE_I', 'invest.settings')

application = get_wsgi_application()