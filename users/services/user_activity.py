from django.utils import timezone
from typing import Optional, List, Dict, Any
from ..models import UserActivity, User


class UserActivityService:
    """Service for UserActivity model operations"""
    
    ACTION_TYPES = [
        ("login", "Login"),
        ("logout", "Logout"),
        ("update_profile", "Update Profile"),
        ("create_post", "Create Post"),
        ("like_post", "Like Post"),
        ("comment", "Comment"),
        ("follow", "Follow"),
        ("unfollow", "Unfollow"),
        ("join_group", "Join Group"),
        ("leave_group", "Leave Group"),
    ]
    
    @staticmethod
    def log_activity(
        user: User,
        action: str,
        description: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        location: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UserActivity:
        """Log user activity"""
        activity = UserActivity.objects.create(
            user=user,
            action=action,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            location=location,
            metadata=metadata or {}
        )
        return activity
    
    @staticmethod
    def get_user_activities(
        user: User,
        action: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[UserActivity]:
        """Get activities for a user"""
        queryset = UserActivity.objects.filter(user=user)
        
        if action:
            queryset = queryset.filter(action=action)
        
        return list(queryset.order_by('-timestamp')[offset:offset + limit])
    
    @staticmethod
    def get_recent_activities(
        limit: int = 100,
        action: Optional[str] = None,
        user: Optional[User] = None
    ) -> List[UserActivity]:
        """Get recent activities across all users"""
        queryset = UserActivity.objects.all()
        
        if action:
            queryset = queryset.filter(action=action)
        if user:
            queryset = queryset.filter(user=user)
        
        return list(queryset.order_by('-timestamp')[:limit])
    
    @staticmethod
    def get_following_activities(
        user: User,
        limit: int = 50
    ) -> List[UserActivity]:
        """Get activities from users that the given user follows"""
        from .user_follow import UserFollowService
        
        following_users = UserFollowService.get_following(user)
        
        return list(UserActivity.objects.filter(
            user__in=following_users
        ).order_by('-timestamp')[:limit])
    
    @staticmethod
    def cleanup_old_activities(days: int = 365) -> int:
        """Delete activities older than specified days"""
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        old_activities = UserActivity.objects.filter(
            timestamp__lt=time_threshold
        )
        count = old_activities.count()
        old_activities.delete()
        return count