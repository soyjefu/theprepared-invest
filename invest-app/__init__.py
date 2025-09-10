# invest-app/__init__.py

# Django가 시작될 때 Celery 앱이 항상 로드되도록 합니다.
from autotrader.celery import app as celery_app

__all__ = ('celery_app',)
