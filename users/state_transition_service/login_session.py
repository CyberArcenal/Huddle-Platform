from users.services.security_log import SecurityLogService
from users.services.blacklisted_access_token import BlacklistedAccessTokenService
from django.utils import timezone


class LoginSessionStateTransitionService:
    """Handles side effects of login session deactivation."""

    @staticmethod
    def handle_session_deactivated(session):
        """Called when a session becomes inactive."""
        # 1. Log a security event
        SecurityLogService.create_log(
            user=session.user,
            event_type='logout' if session.is_valid else 'session_expired',
            ip_address=session.ip_address,
            user_agent=session.device_name,  # or you might store user_agent separately
            details=f'Session {session.id} deactivated. Device: {session.device_name}'
        )

        # 2. Blacklist the refresh token (if it exists and not already blacklisted)
        if session.refresh_token:
            BlacklistedAccessTokenService.blacklist_token(
                jti=session.refresh_token,
                user=session.user,
                expires_at=session.expires_at
            )

        # 3. Blacklist the access token (if it exists)
        if session.access_token:
            BlacklistedAccessTokenService.blacklist_token(
                jti=session.access_token,
                user=session.user,
                expires_at=timezone.now() + timezone.timedelta(minutes=5)  # short expiry for access token
            )

        # Note: The actual removal of the session from active list is already done
        # by setting is_active=False. No further action needed.