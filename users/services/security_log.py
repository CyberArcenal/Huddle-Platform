from django.utils import timezone
from typing import Optional, List, Dict, Any
from ..models import SecurityLog, User


class SecurityLogService:
    """Service for SecurityLog model operations"""
    
    EVENT_TYPES = [
        ("login", "Login"),
        ("logout", "Logout"),
        ("password_change", "Password Change"),
        ("2fa_enabled", "2FA Enabled"),
        ("2fa_disabled", "2FA Disabled"),
        ("failed_login", "Failed Login"),
    ]
    
    @staticmethod
    def create_log(
        user: User,
        event_type: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[str] = None
    ) -> SecurityLog:
        """Create a new security log entry"""
        log = SecurityLog.objects.create(
            user=user,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )
        return log
    
    @staticmethod
    def get_user_logs(
        user: User,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[SecurityLog]:
        """Get security logs for a user"""
        queryset = SecurityLog.objects.filter(user=user)
        
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_failed_login_attempts(
        user: User,
        hours: int = 24
    ) -> List[SecurityLog]:
        """Get failed login attempts within specified hours"""
        time_threshold = timezone.now() - timezone.timedelta(hours=hours)
        
        return list(SecurityLog.objects.filter(
            user=user,
            event_type='failed_login',
            created_at__gte=time_threshold
        ).order_by('-created_at'))
    
    @staticmethod
    def count_failed_login_attempts(
        user: User,
        hours: int = 24
    ) -> int:
        """Count failed login attempts within specified hours"""
        time_threshold = timezone.now() - timezone.timedelta(hours=hours)
        
        return SecurityLog.objects.filter(
            user=user,
            event_type='failed_login',
            created_at__gte=time_threshold
        ).count()
    
    @staticmethod
    def get_suspicious_activities(
        user: User,
        limit: int = 20
    ) -> List[SecurityLog]:
        """Get suspicious security activities for a user"""
        return list(SecurityLog.objects.filter(
            user=user,
            event_type__in=['failed_login', 'password_change', '2fa_disabled']
        ).order_by('-created_at')[:limit])
    
    @staticmethod
    def cleanup_old_logs(days: int = 90) -> int:
        """Soft delete logs older than specified days"""
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        old_logs = SecurityLog.objects.filter(created_at__lt=time_threshold)
        count = old_logs.count()
        
        for log in old_logs:
            log.delete()  # This will soft delete
        
        return count