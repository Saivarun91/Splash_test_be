import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'imgbackend.settings')

app = Celery('imgbackend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
