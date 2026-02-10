import uuid
from django.utils import timezone
from typing import Optional, List
from ..models import LoginSession, User


class LoginSessionService:
    """Service for LoginSession model operations"""
    
    @staticmethod
    def create_session(
        user: User,
        device_name: str,
        ip_address: str,
        expires_at: timezone.datetime,
        refresh_token_jti: str,
        access_token_jti: Optional[str] = None
    ) -> LoginSession:
        """Create a new login session"""
        session = LoginSession.objects.create(
            user=user,
            device_name=device_name,
            ip_address=ip_address,
            expires_at=expires_at,
            refresh_token=refresh_token_jti,
            access_token=access_token_jti or ''
        )
        return session
    
    @staticmethod
    def get_session_by_refresh_token(refresh_token_jti: str) -> Optional[LoginSession]:
        """Get session by refresh token JTI"""
        try:
            return LoginSession.objects.get(refresh_token=refresh_token_jti)
        except LoginSession.DoesNotExist:
            return None
    
    @staticmethod
    def get_session_by_id(session_id: uuid.UUID) -> Optional[LoginSession]:
        """Get session by ID"""
        try:
            return LoginSession.objects.get(id=session_id)
        except LoginSession.DoesNotExist:
            return None
    
    @staticmethod
    def get_active_user_sessions(user: User) -> List[LoginSession]:
        """Get all active sessions for a user"""
        return list(LoginSession.objects.filter(
            user=user,
            is_active=True,
            expires_at__gt=timezone.now()
        ).order_by('-last_used'))
    
    @staticmethod
    def update_last_used(session: LoginSession) -> LoginSession:
        """Update last used timestamp for session"""
        session.last_used = timezone.now()
        session.save(update_fields=['last_used'])
        return session
    
    @staticmethod
    def update_access_token(session: LoginSession, access_token_jti: str) -> LoginSession:
        """Update access token JTI for session"""
        session.access_token = access_token_jti
        session.save(update_fields=['access_token', 'last_used'])
        return session
    
    @staticmethod
    def deactivate_session(session: LoginSession) -> LoginSession:
        """Deactivate a session"""
        session.is_active = False
        session.save(update_fields=['is_active'])
        
        # Blacklist the refresh token
        from .blacklisted_access_token import BlacklistedAccessTokenService
        BlacklistedAccessTokenService.blacklist_token(
            jti=session.refresh_token,
            user=session.user,
            expires_at=session.expires_at
        )
        
        return session
    
    @staticmethod
    def deactivate_all_user_sessions(user: User, exclude_session_id: Optional[uuid.UUID] = None):
        """Deactivate all sessions for a user, optionally excluding one"""
        sessions = LoginSession.objects.filter(
            user=user,
            is_active=True
        )
        
        if exclude_session_id:
            sessions = sessions.exclude(id=exclude_session_id)
        
        # Blacklist all refresh tokens first
        from .blacklisted_access_token import BlacklistedAccessTokenService
        for session in sessions:
            BlacklistedAccessTokenService.blacklist_token(
                jti=session.refresh_token,
                user=session.user,
                expires_at=session.expires_at
            )
        
        # Deactivate sessions
        sessions.update(is_active=False)
    
    @staticmethod
    def cleanup_expired_sessions() -> int:
        """Deactivate expired sessions and return count"""
        expired_sessions = LoginSession.objects.filter(
            expires_at__lt=timezone.now(),
            is_active=True
        )
        
        count = expired_sessions.count()
        expired_sessions.update(is_active=False)
        return count