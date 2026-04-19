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
    'reset-stuck-processing-posts-every-10-minutes': {
        'task': 'feed.tasks.cleanup.reset_stuck_processing_posts',
        'schedule': crontab(minute='*/10'),  # every 10 minutes
        'args': (10,),  # minutes threshold
    },
    # ← NEW TASK: Regenerate broken media variants (every 30 minutes)
    'regenerate-broken-media-variants-every-30-min': {
        'task': 'feed.tasks.media.regenerate_broken_media_variants',
        'schedule': crontab(minute='*/30'),        # every 30 minutes
        'kwargs': {
            'limit': 25,           # process only 25 items per run
            'only_reels': True,    # focus muna sa reels (pwede mo alisin pag stable na)
            'force': False,        # False = only broken ones
        },
    },
    'delete-corrupted-reels-every-hour': {
        'task': 'feed.tasks.reel.delete_corrupted_reels',
        'schedule': crontab(minute=0, hour='*/1'),  # every 1 hour
        'kwargs': {
            'minutes_stuck': 15,
            'soft_delete': True,
            'dry_run': False,
        },
    },
}

