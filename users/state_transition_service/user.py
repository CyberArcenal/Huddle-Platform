from django.utils import timezone
from users.services.security_log import SecurityLogService
from users.services.login_session import LoginSessionService
# Import any other needed services


class UserStateTransitionService:
    """Handles side effects of user state changes."""

    @staticmethod
    def handle_user_created(user):
        """Called when a new user is created."""
        SecurityLogService.create_log(
            user=user,
            event_type='signup',
            details='User registered successfully'
        )
        # Optional: send welcome notification
        # NotificationService.send_welcome_notification(user)

    @staticmethod
    def handle_status_change(user, old_status, new_status):
        """User status (ACTIVE, RESTRICTED, SUSPENDED, DELETED) changed."""
        SecurityLogService.create_log(
            user=user,
            event_type='status_change',
            details=f'Status changed from {old_status} to {new_status}'
        )

        if new_status in ['suspended', 'deleted']:
            # Revoke all active sessions when suspended or deleted
            LoginSessionService.deactivate_all_user_sessions(user)

        # Notify user about the status change
        # NotificationService.send_status_change_notification(user, old_status, new_status)

    @staticmethod
    def handle_is_active_change(user, old_active, new_active):
        """User's is_active flag changed."""
        SecurityLogService.create_log(
            user=user,
            event_type='active_status_change',
            details=f'is_active changed from {old_active} to {new_active}'
        )

        if not new_active:
            # User deactivated – terminate all sessions
            LoginSessionService.deactivate_all_user_sessions(user)

    @staticmethod
    def handle_is_verified_change(user, old_verified, new_verified):
        """User verification status changed."""
        SecurityLogService.create_log(
            user=user,
            event_type='verification_change',
            details=f'Verified changed from {old_verified} to {new_verified}'
        )

        if new_verified:
            # Send congratulatory notification
            # NotificationService.send_verification_success_notification(user)
            pass

    @staticmethod
    def handle_is_staff_change(user, old_staff, new_staff):
        """User staff status changed."""
        SecurityLogService.create_log(
            user=user,
            event_type='staff_status_change',
            details=f'Staff status changed from {old_staff} to {new_staff}'
        )
        # Usually no further action needed, just audit log.