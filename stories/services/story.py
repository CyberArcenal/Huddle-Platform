from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from typing import Optional, List, Dict, Any
from ..models import Story, User
import uuid


class StoryService:
    """Service for Story model operations"""
    
    @staticmethod
    def create_story(
        user: User,
        story_type: str,
        content: Optional[str] = None,
        media_file: Optional[str] = None,
        expires_in_hours: int = 24,
        **extra_fields
    ) -> Story:
        """Create a new story"""
        # Validate story type
        valid_types = [choice[0] for choice in Story.STORY_TYPES]
        if story_type not in valid_types:
            raise ValidationError(f"Invalid story type. Must be one of {valid_types}")
        
        # Validate based on story type
        if story_type == 'text' and not content:
            raise ValidationError("Text stories require content")
        elif story_type in ['image', 'video'] and not media_file:
            raise ValidationError(f"{story_type.capitalize()} stories require media_file")
        
        # Calculate expiration time
        expires_at = timezone.now() + timezone.timedelta(hours=expires_in_hours)
        
        try:
            with transaction.atomic():
                story = Story.objects.create(
                    user=user,
                    story_type=story_type,
                    content=content,
                    media_url=media_file,
                    expires_at=expires_at,
                    **extra_fields
                )
                return story
        except IntegrityError as e:
            raise ValidationError(f"Failed to create story: {str(e)}")
    
    @staticmethod
    def get_story_by_id(story_id: int) -> Optional[Story]:
        """Retrieve story by ID"""
        try:
            return Story.objects.get(id=story_id)
        except Story.DoesNotExist:
            return None
    
    @staticmethod
    def get_active_stories(
        user: Optional[User] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Story]:
        """Get active stories (not expired and is_active=True)"""
        queryset = Story.objects.filter(
            is_active=True,
            expires_at__gt=timezone.now()
        ).select_related('user')
        
        if user:
            queryset = queryset.filter(user=user)
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_user_stories(
        user: User,
        include_expired: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Story]:
        """Get stories by a specific user"""
        queryset = Story.objects.filter(user=user)
        
        if not include_expired:
            queryset = queryset.filter(
                is_active=True,
                expires_at__gt=timezone.now()
            )
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_following_stories(user: User, limit: int = 50) -> List[Dict[str, Any]]:
        """Get stories from users that the given user follows"""
        from users.services import UserFollowService
        
        # Get users that the current user follows
        following_users = UserFollowService.get_following(user)
        
        # Get active stories from these users
        stories = Story.objects.filter(
            user__in=following_users,
            is_active=True,
            expires_at__gt=timezone.now()
        ).select_related('user').order_by('-created_at')[:limit]
        
        # Group stories by user
        user_stories = {}
        for story in stories:
            user_id = story.user.id
            if user_id not in user_stories:
                user_stories[user_id] = {
                    'user': story.user,
                    'stories': []
                }
            user_stories[user_id]['stories'].append(story)
        
        return list(user_stories.values())
    
    @staticmethod
    def update_story(story: Story, update_data: Dict[str, Any]) -> Story:
        """Update story information"""
        try:
            with transaction.atomic():
                for field, value in update_data.items():
                    if hasattr(story, field) and field not in ['id', 'user', 'created_at']:
                        setattr(story, field, value)
                
                story.full_clean()
                story.save()
                return story
        except ValidationError as e:
            raise
    
    @staticmethod
    def deactivate_story(story: Story) -> Story:
        """Deactivate a story (soft delete)"""
        story.is_active = False
        story.save()
        return story
    
    @staticmethod
    def delete_story(story: Story) -> bool:
        """Permanently delete a story"""
        try:
            story.delete()
            return True
        except Exception:
            return False
    
    @staticmethod
    def extend_story_life(story: Story, additional_hours: int = 24) -> Story:
        """Extend the expiration time of a story"""
        if story.expires_at > timezone.now():
            story.expires_at = story.expires_at + timezone.timedelta(hours=additional_hours)
        else:
            story.expires_at = timezone.now() + timezone.timedelta(hours=additional_hours)
        
        story.save()
        return story
    
    @staticmethod
    def get_expired_stories() -> List[Story]:
        """Get all expired stories"""
        return list(Story.objects.filter(
            expires_at__lte=timezone.now()
        ))
    
    @staticmethod
    def cleanup_expired_stories(deactivate_only: bool = True) -> Dict[str, int]:
        """Clean up expired stories"""
        expired_stories = Story.objects.filter(
            expires_at__lte=timezone.now(),
            is_active=True
        )
        
        stats = {
            'total': expired_stories.count(),
            'deactivated': 0,
            'deleted': 0
        }
        
        if deactivate_only:
            # Soft delete: deactivate stories
            stats['deactivated'] = expired_stories.update(is_active=False)
        else:
            # Hard delete: permanently remove
            deleted_info = expired_stories.delete()
            stats['deleted'] = deleted_info[0] if deleted_info else 0
        
        return stats
    
    @staticmethod
    def get_story_stats(user: User) -> Dict[str, int]:
        """Get statistics about user's stories"""
        now = timezone.now()
        
        return {
            'total_stories': Story.objects.filter(user=user).count(),
            'active_stories': Story.objects.filter(
                user=user,
                is_active=True,
                expires_at__gt=now
            ).count(),
            'expired_stories': Story.objects.filter(
                user=user,
                expires_at__lte=now
            ).count(),
            'total_views': sum(
                story.views.count() 
                for story in Story.objects.filter(user=user)
            )
        }
    
    @staticmethod
    def get_stories_by_type(
        story_type: str,
        active_only: bool = True,
        limit: int = 50
    ) -> List[Story]:
        """Get stories by type"""
        queryset = Story.objects.filter(story_type=story_type)
        
        if active_only:
            queryset = queryset.filter(
                is_active=True,
                expires_at__gt=timezone.now()
            )
        
        return list(queryset.order_by('-created_at')[:limit])