import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from messaging.models import Conversation


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'

        # Ensure user is authenticated
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close()
            return

        # Check if user is a participant
        if not await self.is_participant(user, self.conversation_id):
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

    # No receive method – all messages come via HTTP and are broadcast from the view

    async def chat_message(self, event):
        """
        Called when the view sends a message to the group.
        Sends the message data to the WebSocket client.
        """
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'message_id': event['message_id'],
            'sender_id': event['sender_id'],
            'sender_username': event['sender_username'],
            'content': event['content'],
            'media_url': event['media_url'],
            'media_type': event['media_type'],
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def is_participant(self, user, conversation_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            return user in conversation.participants.all()
        except Conversation.DoesNotExist:
            return False