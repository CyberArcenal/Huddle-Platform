from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from typing import Optional, List, Tuple

from users.enums import UserStatus
from ..models import User, UserFollow


class UserFollowService:
    """Service for UserFollow model operations"""
    
    @staticmethod
    def follow_user(follower: User, following: User) -> Tuple[bool, Optional[UserFollow]]:
        """Follow another user"""
        if follower == following:
            raise ValidationError("Cannot follow yourself")
        
        try:
            with transaction.atomic():
                follow, created = UserFollow.objects.get_or_create(
                    follower=follower,
                    following=following
                )
                return created, follow
        except IntegrityError:
            # Already following
            return False, UserFollow.objects.get(
                follower=follower,
                following=following
            )
    
    @staticmethod
    def unfollow_user(follower: User, following: User) -> bool:
        """Unfollow a user"""
        try:
            rows_deleted, _ = UserFollow.objects.filter(
                follower=follower,
                following=following
            ).delete()
            return rows_deleted > 0
        except Exception:
            return False
    
    @staticmethod
    def is_following(follower: User, following: User) -> bool:
        """Check if user is following another user"""
        return UserFollow.objects.filter(
            follower=follower,
            following=following
        ).exists()
    
    @staticmethod
    def get_followers(user: User, limit: int = 50) -> List[User]:
        """Get users who follow the given user"""
        follower_ids = UserFollow.objects.filter(
            following=user
        ).values_list('follower_id', flat=True)[:limit]
        
        return User.objects.filter(id__in=follower_ids)
    
    @staticmethod
    def get_following(user: User, limit: int = 50) -> List[User]:
        """Get users followed by the given user"""
        following_ids = UserFollow.objects.filter(
            follower=user
        ).values_list('following_id', flat=True)[:limit]
        
        return User.objects.filter(id__in=following_ids)
    
    @staticmethod
    def get_follower_count(user: User) -> int:
        """Get number of followers"""
        return UserFollow.objects.filter(following=user).count()
    
    @staticmethod
    def get_following_count(user: User) -> int:
        """Get number of users being followed"""
        return UserFollow.objects.filter(follower=user).count()
    
    @staticmethod
    def get_mutual_follows(user1: User, user2: User) -> List[User]:
        """Get mutual followers between two users"""
        user1_following = set(UserFollowService.get_following(user1))
        user2_following = set(UserFollowService.get_following(user2))
        
        return list(user1_following.intersection(user2_following))
    
    @staticmethod
    def get_suggested_users(user: User, limit: int = 10) -> List[User]:
        """Get suggested users to follow based on mutual follows"""
        # Get users followed by people you follow
        following_ids = UserFollow.objects.filter(
            follower=user
        ).values_list('following_id', flat=True)
        
        if not following_ids:
            # If not following anyone, suggest random active users
            return User.objects.filter(
                status=UserStatus.ACTIVE
            ).exclude(
                id=user.id
            ).order_by('?')[:limit]
        
        suggested_ids = UserFollow.objects.filter(
            follower_id__in=following_ids
        ).exclude(
            following_id=user.id
        ).values_list('following_id', flat=True).distinct()[:limit]
        
        return User.objects.filter(id__in=suggested_ids)