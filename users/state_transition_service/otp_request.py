from users.services.security_log import SecurityLogService


class OtpRequestStateTransitionService:
    """Handles side effects when an OTP is used."""

    @staticmethod
    def handle_otp_used(otp_request):
        """Called when an OTP is marked as used."""
        # 1. Log verification event
        SecurityLogService.create_log(
            user=otp_request.user,
            event_type='otp_verified',
            ip_address=None,  # IP can be captured from request context if available
            user_agent=None,
            details=f'OTP used for {otp_request.type}: {otp_request.email or otp_request.phone}'
        )

        # No further action needed; the OTP is now invalid for reuse.