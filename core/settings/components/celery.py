# Celery Configuration
#/settings/component/celery.py
import os

from celery.schedules import crontab

MEDIA_PROCESSING_USE_CELERY = True

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")  # Redis container sa Docker Compose
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Manila"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
SYNC_INTERVAL = int(os.getenv('LIVE_SYNC_INTERVAL_SECONDS', 60))



CELERY_BEAT_SCHEDULE = {
    'sync-live-streams-every-minute': {
        'task': 'live.tasks.live.sync_live_streams_status',
        'schedule': SYNC_INTERVAL,
        'options': {
            'expires': SYNC_INTERVAL - 5,
        }
    },
}

