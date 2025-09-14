# invest-app/invest/celery.py

# Numba Caching 버그 수정을 위한 Monkey Patch 적용
# 이 import는 다른 라이브러리(예: pandas_ta)가 numba를 import하기 전에 실행되어야 합니다.
import invest.numba_patch

import os
from celery import Celery

# Django의 settings 모듈을 Celery의 기본 설정으로 사용합니다.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'invest.settings')

app = Celery('invest')

# 'CELERY' 네임스페이스를 사용하여 Django 설정 파일에서 Celery 설정을 로드합니다.
# 예: CELERY_BROKER_URL
app.config_from_object('django.conf:settings', namespace='CELERY')

# Django 앱 설정에서 task를 자동으로 찾습니다.
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')