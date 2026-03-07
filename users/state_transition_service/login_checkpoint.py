from users.services.security_log import SecurityLogService


class LoginCheckpointStateTransitionService:
    """Handles side effects when a login checkpoint is used."""

    @staticmethod
    def handle_checkpoint_used(checkpoint):
        """Called when a checkpoint is marked as used."""
        # 1. Log verification event
        SecurityLogService.create_log(
            user=checkpoint.user,
            event_type='checkpoint_verified',
            ip_address=None,
            user_agent=None,
            details=f'Login checkpoint used for {checkpoint.email or checkpoint.user}'
        )

        # No further action; checkpoint cannot be reused.