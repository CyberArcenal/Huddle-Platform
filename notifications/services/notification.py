from notifications.models import Notification
from users.models import User
from django.db import transaction
from typing import Optional


class NotificationService:
    """Service for creating and managing notifications."""

    @staticmethod
    def create_notification(
        user: User,
        actor: User,
        notification_type: str,
        message: str,
        related_id: Optional[int] = None,
        related_model: Optional[str] = None
    ) -> Notification:
        """Create a new notification record."""
        return Notification.objects.create(
            user=user,
            actor=actor,
            notification_type=notification_type,
            message=message,
            related_id=related_id,
            related_model=related_model
        )

    @staticmethod
    def send_report_outcome_notification(user: User, report, outcome: str):
        """Notify a user about the outcome of a report they submitted."""
        message = f"Your report (ID: {report.id}) has been {outcome}."
        NotificationService.create_notification(
            user=user,
            actor=None,  # system notification
            notification_type='report_outcome',
            message=message,
            related_id=report.id,
            related_model='ReportedContent'
        )

    @staticmethod
    def send_status_change_notification(user: User, old_status: str, new_status: str):
        """Notify a user that their account status has changed."""
        message = f"Your account status changed from {old_status} to {new_status}."
        NotificationService.create_notification(
            user=user,
            actor=None,
            notification_type='account_status',
            message=message
        )

    @staticmethod
    def send_verification_success_notification(user: User):
        """Notify a user that their email/account has been verified."""
        message = "Your account has been successfully verified!"
        NotificationService.create_notification(
            user=user,
            actor=None,
            notification_type='account_verified',
            message=message
        )

    @staticmethod
    def send_welcome_notification(user: User):
        """Send a welcome notification to a new user."""
        message = "Welcome to Huddle! We're glad to have you."
        NotificationService.create_notification(
            user=user,
            actor=None,
            notification_type='welcome',
            message=message
        )

    @staticmethod
    def send_post_deleted_notification(user_id: int, post):
        """Notify a user that a post they commented on has been deleted."""
        from users.models import User
        try:
            user = User.objects.get(id=user_id)
            message = f"A post you commented on (ID: {post.id}) has been deleted."
            NotificationService.create_notification(
                user=user,
                actor=None,
                notification_type='post_deleted',
                message=message,
                related_id=post.id,
                related_model='Post'
            )
        except User.DoesNotExist:
            pass

    @staticmethod
    def send_rsvp_change_notification(organizer: User, event, attendee: User, old_status: str, new_status: str):
        """Notify event organizer when someone changes their RSVP."""
        message = f"{attendee.get_full_name() or attendee.username} changed their RSVP from {old_status or 'none'} to {new_status} for event '{event.title}'."
        NotificationService.create_notification(
            user=organizer,
            actor=attendee,
            notification_type='rsvp_change',
            message=message,
            related_id=event.id,
            related_model='Event'
        )