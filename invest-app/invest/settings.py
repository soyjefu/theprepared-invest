# invest-app/invest/settings.py

import os
from pathlib import Path
from celery.schedules import crontab # 수정: crontab import 추가

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ... (기존 설정은 모두 동일) ...

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-default-secret-key-for-development')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']
CSRF_TRUSTED_ORIGINS = ['https://stock.theprepared.kr']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    # 3rd Party Apps
    'rest_framework',
    'django_celery_beat',
    # Local Apps
    'trading',
]

# ... (MIDDLEWARE, ROOT_URLCONF, TEMPLATES 등은 동일) ...
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'invest.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
WSGI_APPLICATION = 'invest.wsgi.application'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB_I'),
        'USER': os.environ.get('POSTGRES_USER'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'HOST': 'postgres_db',
        'PORT': 5432,
    }
}
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Redis Cache Settings
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Celery Settings
CELERY_BROKER_URL = 'redis://redis:6379/0'
CELERY_RESULT_BACKEND = 'redis://redis:6379/0'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Seoul'

# Celery Beat (Periodic Tasks) Settings
CELERY_BEAT_SCHEDULE = {
    # 매일 새벽 4시에 1차, 2차 분석 실행
    'run-daily-morning-routine': {
        'task': 'trading.tasks.run_daily_morning_routine',
        'schedule': crontab(minute=0, hour=4), # 매일 새벽 4시에 실행
    },
    # 2. 매일 오전 8시 55분에 2차 AI 분석 실행
    'analyze-stocks-daily': {
        'task': 'trading.tasks.analyze_stocks_task',
        'schedule': crontab(hour=8, minute=55, day_of_week='1-5'),
    },
    # 3. 매일 오전 9시 5분에 3차 매매 실행
    'execute-trades-daily': {
        'task': 'trading.tasks.execute_ai_trades_task',
        'schedule': crontab(hour=9, minute=5, day_of_week='1-5'),
    },
    # 4. 매일 장중 1분마다 포지션 모니터링 실행
    'monitor-positions-intraday': {
        'task': 'trading.tasks.monitor_open_positions_task',
        'schedule': crontab(hour='9-15', minute='*', day_of_week='1-5'),
    },
}   