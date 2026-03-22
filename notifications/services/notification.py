import json
import logging
from django.utils import timezone
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings

from notifications.models.notification import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service for creating in-app notifications and logging notification attempts.
    """

    @staticmethod
    def create_notification(user, title, message, notif_type='info', metadata=None):
        """
        Create an in-app notification for a specific user.

        Args:
            user: User instance (required).
            title (str): Notification title.
            message (str): Notification message.
            notif_type (str): One of Notification.TYPE_CHOICES (default: 'info').
            metadata (dict, optional): Additional JSON-serializable data.

        Returns:
            Notification: The created notification instance.
        """
        if not user:
            logger.warning("Attempted to create notification without user")
            return None

        try:
            with transaction.atomic():
                notification = Notification.objects.create(
                    user=user,
                    title=title,
                    message=message,
                    type=notif_type,
                    metadata=metadata or {}
                )
            logger.info(f"Notification created for user {user.id}: {title}")
            return notification
        except Exception as e:
            logger.error(f"Failed to create notification: {e}")
            return None

    @staticmethod
    def create_notification_for_staff(title, message, notif_type='info', metadata=None):
        """
        Create notifications for all staff users (or a subset).
        Useful for system-wide announcements.

        Args:
            title (str): Notification title.
            message (str): Notification message.
            notif_type (str): Type of notification.
            metadata (dict, optional): Additional data.

        Returns:
            list: List of created Notification instances.
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        staff_users = User.objects.filter(is_staff=True)
        created = []
        for user in staff_users:
            notif = NotificationService.create_notification(
                user=user,
                title=title,
                message=message,
                notif_type=notif_type,
                metadata=metadata
            )
            if notif:
                created.append(notif)
        return created

    @staticmethod
    def mark_as_read(notification_id, user):
        """
        Mark a notification as read (if it belongs to the user).

        Args:
            notification_id (int): ID of the notification.
            user: User instance.

        Returns:
            bool: True if updated, False otherwise.
        """
        try:
            with transaction.atomic():
                notification = Notification.objects.get(pk=notification_id, user=user)
                if not notification.is_read:
                    notification.is_read = True
                    notification.save(update_fields=['is_read'])
                    logger.info(f"Notification {notification_id} marked as read")
                return True
        except Notification.DoesNotExist:
            logger.warning(f"Notification {notification_id} not found for user {user.id}")
            return False

    @staticmethod
    def mark_all_as_read(user):
        """
        Mark all notifications of a user as read.

        Args:
            user: User instance.

        Returns:
            int: Number of notifications updated.
        """
        updated = Notification.objects.filter(user=user, is_read=False).update(is_read=True)
        logger.info(f"Marked {updated} notifications as read for user {user.id}")
        return updated

