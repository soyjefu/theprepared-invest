# invest-app/invest/wsgi.py

# Numba Caching 버그 수정을 위한 Monkey Patch 적용
# 이 import는 다른 라이브러리(예: pandas_ta)가 numba를 import하기 전에 실행되어야 합니다.
import invest.numba_patch

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