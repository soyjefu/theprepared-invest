# invest-app/invest/__init__.py

# Django가 시작될 때 Celery 앱이 로드되도록 합니다.
from .celery import app as celery_app

__all__ = ('celery_app',)