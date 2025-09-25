"""
Django settings for the invest project.
"""

import os
import sys
from pathlib import Path
from celery.schedules import crontab

# --- Core Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security ---
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-default-secret-key-for-development')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']
CSRF_TRUSTED_ORIGINS = ['https://stock.theprepared.kr']

# --- Application Definitions ---
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
WSGI_APPLICATION = 'invest.wsgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Templates ---
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

# --- Database ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB_I'),
        'USER': os.environ.get('POSTGRES_USER'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'HOST': 'invest_db',
        'PORT': 5432,
    }
}

# --- Password Validation ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True

# --- Static Files ---
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# --- Caching (Redis) ---
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# --- Celery ---
CELERY_BROKER_URL = 'redis://redis:6379/0'
CELERY_RESULT_BACKEND = 'redis://redis:6379/0'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Seoul'

# --- Celery Beat (Periodic Tasks Schedule) ---
CELERY_BEAT_SCHEDULE = {
    # Stage 1: Run initial stock screening daily at 8:50 AM KST (Mon-Fri)
    'run-daily-morning-routine': {
        'task': 'trading.tasks.run_daily_morning_routine',
        'schedule': crontab(hour=8, minute=50, day_of_week='1-5'),
    },
    # Stage 2: Run AI analysis on screened stocks at 8:55 AM KST (Mon-Fri)
    'analyze-stocks-daily': {
        'task': 'trading.tasks.analyze_stocks_task',
        'schedule': crontab(hour=8, minute=55, day_of_week='1-5'),
    },
    # Stage 3: Execute AI-based trades at 9:05 AM KST (Mon-Fri)
    'execute-trades-daily': {
        'task': 'trading.tasks.execute_ai_trades_task',
        'schedule': crontab(hour=9, minute=5, day_of_week='1-5'),
    },
    # Monitor open positions every minute during market hours (9 AM - 3:30 PM KST, Mon-Fri)
    'monitor-positions-intraday': {
        'task': 'trading.tasks.monitor_open_positions_task',
        'schedule': crontab(hour='9-15', minute='*', day_of_week='1-5'),
    },
}

# --- Authentication ---
LOGIN_URL = '/admin/login/'

# --- Testing ---
# Use in-memory database and channel layer for tests to ensure isolation and speed.
if 'test' in sys.argv:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:'
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer"
        }
    }