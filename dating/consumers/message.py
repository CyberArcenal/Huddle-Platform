import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.exceptions import ValidationError
from dating.services.dating_message import DatingMessageService
from users.models import User


class DatingChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.receiver_id = self.scope['url_route']['kwargs']['receiver_id']
        self.room_group_name = f'dating_chat_{sorted([self.scope["user"].id, int(self.receiver_id)])}'

        # Ensure user is authenticated
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close()
            return

        self.user = user

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages (send new dating message)."""
        data = json.loads(text_data)
        content = data.get("content")

        try:
            message = await self.send_message(self.user.id, self.receiver_id, content)
        except ValidationError as e:
            await self.send(text_data=json.dumps({
                "type": "error",
                "errors": e.message_dict if hasattr(e, "message_dict") else str(e),
            }))
            return

        # Broadcast to group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message_id": message.id,
                "sender_id": message.sender.id,
                "sender_username": message.sender.username,
                "receiver_id": message.receiver.id,
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
                "is_read": message.is_read,
            }
        )

    async def chat_message(self, event):
        """Send broadcasted message to WebSocket client."""
        await self.send(text_data=json.dumps({
            "type": "new_message",
            "message_id": event["message_id"],
            "sender_id": event["sender_id"],
            "sender_username": event["sender_username"],
            "receiver_id": event["receiver_id"],
            "content": event["content"],
            "timestamp": event["timestamp"],
            "is_read": event["is_read"],
        }))

    @database_sync_to_async
    def send_message(self, sender_id, receiver_id, content):
        sender = User.objects.get(pk=sender_id)
        receiver = User.objects.get(pk=receiver_id)
        return DatingMessageService.send_message(sender=sender, receiver=receiver, content=content)