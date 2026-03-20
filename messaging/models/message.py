from django.conf import settings
from django.db import models

from messaging.models.conversation import Conversation


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    media = models.FileField(upload_to='chat_media/', blank=True, null=True)
    media_type = models.CharField(max_length=20, blank=True, null=True)  # e.g., 'image', 'video'
    is_read = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messages'
        ordering = ['created_at']