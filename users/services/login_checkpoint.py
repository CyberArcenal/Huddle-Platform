import uuid
from django.utils import timezone
from typing import Optional
from ..models import LoginCheckpoint, User


class LoginCheckpointService:
    """Service for LoginCheckpoint model operations"""
    
    @staticmethod
    def create_checkpoint(
        user: Optional[User] = None,
        email: Optional[str] = None,
        expires_in_minutes: int = 30
    ) -> LoginCheckpoint:
        """Create a new login checkpoint"""
        if not user and not email:
            raise ValueError("Either user or email must be provided")
        
        expires_at = timezone.now() + timezone.timedelta(minutes=expires_in_minutes)
        
        checkpoint = LoginCheckpoint.objects.create(
            user=user,
            email=email,
            expires_at=expires_at
        )
        return checkpoint
    
    @staticmethod
    def get_checkpoint_by_token(token: str) -> Optional[LoginCheckpoint]:
        """Get checkpoint by token"""
        try:
            return LoginCheckpoint.objects.get(token=token)
        except LoginCheckpoint.DoesNotExist:
            return None
    
    @staticmethod
    def validate_checkpoint(token: str) -> Optional[LoginCheckpoint]:
        """Validate checkpoint token and return if valid"""
        checkpoint = LoginCheckpointService.get_checkpoint_by_token(token)
        
        if checkpoint and checkpoint.is_valid:
            return checkpoint
        
        return None
    
    @staticmethod
    def mark_checkpoint_used(checkpoint: LoginCheckpoint) -> LoginCheckpoint:
        """Mark checkpoint as used"""
        checkpoint.is_used = True
        checkpoint.save()
        return checkpoint
    
    @staticmethod
    def cleanup_expired_checkpoints() -> int:
        """Delete expired checkpoints and return count"""
        expired_checkpoints = LoginCheckpoint.objects.filter(
            expires_at__lt=timezone.now()
        )
        count = expired_checkpoints.count()
        expired_checkpoints.delete()
        return count
    
    @staticmethod
    def get_user_checkpoints(user: User, limit: int = 10) -> list:
        """Get recent checkpoints for a user"""
        return list(LoginCheckpoint.objects.filter(
            user=user
        ).order_by('-created_at')[:limit])