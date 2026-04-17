from django.db import transaction
from django.core.exceptions import ValidationError
from typing import List, Optional
from ..models import DatingMessage, User


class DatingMessageService:
    """Service layer for DatingMessage model operations."""

    @staticmethod
    def send_message(sender: User, receiver: User, content: str) -> DatingMessage:
        """Send a new dating message."""
        if sender.id == receiver.id:
            raise ValidationError("Cannot send a message to yourself.")

        if not content.strip():
            raise ValidationError("Message content cannot be empty.")

        with transaction.atomic():
            message = DatingMessage.objects.create(
                sender=sender,
                receiver=receiver,
                content=content.strip(),
                is_read=False,
            )
            return message

    @staticmethod
    def mark_as_read(message: DatingMessage) -> DatingMessage:
        """Mark a message as read."""
        if not message.is_read:
            message.is_read = True
            message.save()
        return message

    @staticmethod
    def get_conversation(user1: User, user2: User) -> List[DatingMessage]:
        """Retrieve all messages between two users, ordered by creation time."""
        return DatingMessage.objects.filter(
            sender=user1, receiver=user2
        ).union(
            DatingMessage.objects.filter(sender=user2, receiver=user1)
        ).order_by("created_at")

    @staticmethod
    def list_inbox(user: User) -> List[DatingMessage]:
        """List all received messages for a user."""
        return DatingMessage.objects.filter(receiver=user).order_by("-created_at")

    @staticmethod
    def list_sent(user: User) -> List[DatingMessage]:
        """List all sent messages for a user."""
        return DatingMessage.objects.filter(sender=user).order_by("-created_at")

    @staticmethod
    def get_message(message_id: int) -> Optional[DatingMessage]:
        """Retrieve a specific message by ID."""
        try:
            return DatingMessage.objects.get(pk=message_id)
        except DatingMessage.DoesNotExist:
            return None