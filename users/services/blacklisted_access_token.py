from django.utils import timezone
from typing import Optional
from ..models import BlacklistedAccessToken, User


class BlacklistedAccessTokenService:
    """Service for BlacklistedAccessToken model operations"""
    
    @staticmethod
    def blacklist_token(jti: str, user: User, expires_at: timezone.datetime) -> BlacklistedAccessToken:
        """Blacklist a JWT token"""
        token, created = BlacklistedAccessToken.objects.get_or_create(
            jti=jti,
            defaults={
                'user': user,
                'expires_at': expires_at
            }
        )
        return token
    
    @staticmethod
    def is_token_blacklisted(jti: str) -> bool:
        """Check if a token is blacklisted"""
        return BlacklistedAccessToken.objects.filter(jti=jti).exists()
    
    @staticmethod
    def get_blacklisted_token(jti: str) -> Optional[BlacklistedAccessToken]:
        """Retrieve blacklisted token by jti"""
        try:
            return BlacklistedAccessToken.objects.get(jti=jti)
        except BlacklistedAccessToken.DoesNotExist:
            return None
    
    @staticmethod
    def remove_blacklisted_token(jti: str) -> bool:
        """Remove a token from blacklist"""
        deleted_count, _ = BlacklistedAccessToken.objects.filter(jti=jti).delete()
        return deleted_count > 0
    
    @staticmethod
    def cleanup_expired_tokens() -> int:
        """Remove expired blacklisted tokens and return count"""
        expired_tokens = BlacklistedAccessToken.objects.filter(
            expires_at__lt=timezone.now()
        )
        count = expired_tokens.count()
        expired_tokens.delete()
        return count
    
    @staticmethod
    def get_user_blacklisted_tokens(user: User) -> list:
        """Get all blacklisted tokens for a user"""
        return list(BlacklistedAccessToken.objects.filter(user=user))