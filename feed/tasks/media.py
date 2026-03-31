# feed/tasks.py
from celery import shared_task
from PIL import Image
from django.core.files import File
import os

from feed.services.media import MediaProcessingService

@shared_task
def process_media_task(media_id:int) -> None:
    from feed.models import Media
    try:
        media = Media.objects.get(id=media_id)
        MediaProcessingService.process_media(media)
    except Media.DoesNotExist:
        pass