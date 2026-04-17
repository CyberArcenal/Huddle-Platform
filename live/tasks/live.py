# live/tasks/live.py
import logging
from celery import shared_task
from django.utils import timezone
from live.models.live import LiveStream
from live.services.livekit import is_room_active
from live.services.live import LiveService

logger = logging.getLogger(__name__)

@shared_task
def sync_live_streams_status():
    """Check all live streams if their LiveKit room is still active. If not, end the stream."""
    streams = LiveStream.objects.filter(status='live')
    for live in streams:
        if not live.livekit_room:
            # Walang room, dapat hindi live
            logger.warning(f"Live stream {live.id} has no livekit_room but status=live. Ending.")
            LiveService.end_live(live, live.host)
            continue
        
        try:
            active = is_room_active(live.livekit_room)
        except Exception as e:
            logger.error(f"Failed to check room {live.livekit_room}: {e}")
            continue
        
        if not active:
            logger.info(f"LiveKit room {live.livekit_room} is gone. Ending live stream {live.id}")
            LiveService.end_live(live, live.host)