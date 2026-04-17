# live/management/commands/sync_live_status.py
from django.core.management.base import BaseCommand
from live.models.live import LiveStream
from live.services.livekit import is_room_active  # need to implement
from live.services.live import LiveService

class Command(BaseCommand):
    def handle(self, *args, **options):
        for live in LiveStream.objects.filter(status='live'):
            if live.livekit_room:
                active = is_room_active(live.livekit_room)
                if not active:
                    LiveService.end_live(live, live.host)  # host can be live.host
                    self.stdout.write(f"Ended stale stream {live.id}")