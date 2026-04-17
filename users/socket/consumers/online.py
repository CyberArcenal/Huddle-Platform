import json
import redis
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.utils import timezone


User = get_user_model()
# Redis client for online status
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

class OnlineStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Extract token from query string
        query_string = self.scope['query_string'].decode()
        token = None
        for param in query_string.split('&'):
            if param.startswith('token='):
                token = param.split('=')[1]
                break

        if not token:
            await self.close()
            return

        # Authenticate user
        user = await self.get_user_from_token(token)
        if not user:
            await self.close()
            return

        self.user = user
        self.group_name = f"user_{user.id}_online"

        # Accept connection
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Mark user online in Redis (with 60s TTL)
        redis_client.setex(f"online:{user.id}", 60, "1")
        # Also update last_seen in DB (optional)
        await self.update_last_seen(user)

        # Broadcast to others that this user came online
        await self.channel_layer.group_send(
            "global_online",
            {
                "type": "user_status",
                "user_id": user.id,
                "status": "online"
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'user'):
            # Remove from Redis (will expire anyway)
            redis_client.delete(f"online:{self.user.id}")
            # Leave group
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            # Broadcast offline
            await self.channel_layer.group_send(
                "global_online",
                {
                    "type": "user_status",
                    "user_id": self.user.id,
                    "status": "offline"
                }
            )

    async def receive(self, text_data):
        # Heartbeat – client sends ping to keep connection alive
        # You can reset Redis TTL here
        if hasattr(self, 'user'):
            redis_client.expire(f"online:{self.user.id}", 60)
            await self.send(json.dumps({"type": "pong"}))

    async def user_status(self, event):
        # Send status updates to connected clients
        await self.send(json.dumps({
            "type": "status_update",
            "user_id": event["user_id"],
            "status": event["status"]
        }))

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except (InvalidToken, TokenError, User.DoesNotExist):
            return None

    @database_sync_to_async
    def update_last_seen(self, user):
        user.last_seen = timezone.now()
        user.save(update_fields=['last_seen'])