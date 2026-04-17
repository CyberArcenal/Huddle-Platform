import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from live.services.live import LiveService
from live.models.live import LiveStream, LiveParticipant


class LiveConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = None          # Initialize to None
        self.live_id = None
        self.room_group_name = None

    async def connect(self):
        self.live_id = self.scope['url_route']['kwargs']['live_id']
        self.room_group_name = f'live_{self.live_id}'

        # Resolve user
        user = self.scope['user']
        if user.is_anonymous:
            await self.close()
            return
        self.user = user
        self.user_id = user.id       # Store ID for later use

        live = await self.get_live()
        if not live or live.status != 'live':
            await self.close()
            return

        is_host = (live.host_id == self.user_id)
        is_participant = await self.is_participant()
        has_pending = await self.has_pending_request()

        if not (is_host or is_participant or has_pending):
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        if is_participant:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'participant_update',
                    'action': 'join',
                    'user_id': self.user_id,
                    'username': self.user.username,
                }
            )

    async def disconnect(self, close_code):
        # Only perform group operations if we actually joined a group
        if self.room_group_name and hasattr(self, 'channel_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

            # Only attempt participant cleanup if we had a valid user ID
            if self.user_id:
                if await self.is_participant():
                    live = await self.get_live()
                    if live:
                        await self.leave_live(live)
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'participant_update',
                                'action': 'leave',
                                'user_id': self.user_id,
                            }
                        )

    # ---------- Handlers for events from group ----------
    async def new_request(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_request',
            'request': event['request']
        }))

    async def new_comment(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_comment',
            'comment_id': event['comment_id'],
            'user_id': event['user_id'],
            'username': event['username'],
            'content': event['content'],
            'created_at': event['created_at'],
        }))

    async def request_responded(self, event):
        await self.send(text_data=json.dumps({
            'type': 'request_responded',
            'status': event['status'],
            'request_id': event['request_id']
        }))

    async def participant_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'participant_update',
            'action': event['action'],
            'user_id': event.get('user_id'),
            'username': event.get('username')
        }))

    async def stream_ended(self, event):
        await self.send(text_data=json.dumps({'type': 'stream_ended'}))

    # ---------- Database helpers ----------
    @database_sync_to_async
    def get_live(self):
        try:
            return LiveStream.objects.get(id=self.live_id)
        except LiveStream.DoesNotExist:
            return None

    @database_sync_to_async
    def is_participant(self):
        # Use self.user_id, which should be set if this method is called legitimately
        return LiveParticipant.objects.filter(
            live_id=self.live_id,
            user_id=self.user_id,
            left_at__isnull=True
        ).exists()

    @database_sync_to_async
    def has_pending_request(self):
        from live.models.live import LiveJoinRequest
        return LiveJoinRequest.objects.filter(
            live_id=self.live_id,
            user_id=self.user_id,
            status='pending'
        ).exists()

    @database_sync_to_async
    def leave_live(self, live):
        LiveService.leave_live(self.user, live)   # self.user is resolved