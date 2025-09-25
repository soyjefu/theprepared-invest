"""
Celery application configuration for the invest project.

This file configures the Celery instance for the project, allowing background
tasks to be managed and executed. It sets up the Django settings as the
source for Celery's configuration and automatically discovers task modules
in all registered Django apps.
"""

# Apply a monkey patch to fix a Numba caching bug before any other
# library (like pandas_ta) can import numba.
import invest.numba_patch

import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'invest.settings')

# Create the Celery application instance.
app = Celery('invest')

# Load Celery configuration from Django settings, using a 'CELERY' namespace.
# This means all Celery settings in settings.py should be prefixed with 'CELERY_'.
# Example: CELERY_BROKER_URL
app.config_from_object('django.conf:settings', namespace='CELERY')

# Automatically discover and load task modules from all registered Django apps.
# Celery will look for a 'tasks.py' file in each app.
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """
    A sample task for debugging purposes.

    Prints the request information of the task itself to the Celery worker's console.
    """
    print(f'Request: {self.request!r}')