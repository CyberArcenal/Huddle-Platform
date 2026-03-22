import logging
from django.db import transaction

from notifications.models.notify_log import NotifyLog

logger = logging.getLogger(__name__)


class NotificationQueueService:
    """
    Service for queuing notifications via NotifyLog.
    Calling this service creates a NotifyLog entry; the post_save signal
    will then handle the actual delivery based on the channel.
    """

    @staticmethod
    def queue_notification(
        channel: str,
        recipient: str,
        subject: str = None,
        message: str = None,
        priority: str = 'normal',
        metadata: dict = None,
        **extra_fields
    ) -> NotifyLog:
        """
        Create a NotifyLog entry to queue a notification.

        Args:
            channel (str): 'email', 'sms', or 'push'.
            recipient (str): Email address, phone number, or device token.
            subject (str, optional): Subject/title of the notification.
            message (str, optional): Body/payload of the notification.
            priority (str): 'normal' or 'high' (default: 'normal').
            metadata (dict, optional): Additional JSON-serializable data.
            **extra_fields: Any other fields accepted by NotifyLog (e.g., retry_count).

        Returns:
            NotifyLog: The created log instance.
        """
        if not recipient:
            logger.error("Cannot queue notification without recipient")
            return None

        try:
            with transaction.atomic():
                log_entry = NotifyLog.objects.create(
                    channel=channel,
                    recipient_email=recipient,  # Reused for SMS/push tokens
                    subject=subject,
                    payload=message,
                    priority=priority,
                    status='queued',
                    metadata=metadata or {},
                    **extra_fields
                )
            logger.info(
                "Queued %s notification for %s: %s",
                channel, recipient, subject
            )
            return log_entry
        except Exception as e:
            logger.exception("Failed to queue notification: %s", e)
            return None

    @staticmethod
    def queue_bulk_notifications(
        channel: str,
        recipients: list,
        subject: str = None,
        message: str = None,
        priority: str = 'normal',
        **extra_fields
    ) -> list:
        """
        Queue multiple notifications efficiently (bulk create).

        Args:
            channel (str): Notification channel.
            recipients (list): List of recipient strings.
            subject (str, optional): Common subject.
            message (str, optional): Common message.
            priority (str): Priority level.
            **extra_fields: Additional fields (applied to all).

        Returns:
            list: List of created NotifyLog instances.
        """
        if not recipients:
            return []

        logs = []
        try:
            with transaction.atomic():
                objs = [
                    NotifyLog(
                        channel=channel,
                        recipient_email=recipient,
                        subject=subject,
                        payload=message,
                        priority=priority,
                        status='queued',
                        **extra_fields
                    )
                    for recipient in recipients
                ]
                logs = NotifyLog.objects.bulk_create(objs)
            logger.info("Queued %d %s notifications", len(logs), channel)
        except Exception as e:
            logger.exception("Failed to queue bulk notifications: %s", e)
        return logs