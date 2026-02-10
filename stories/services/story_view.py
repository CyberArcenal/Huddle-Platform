from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from typing import Optional, List, Dict, Any
from ..models import Story, StoryView, User


class StoryViewService:
    """Service for StoryView model operations"""
    
    @staticmethod
    def record_view(story: Story, user: User) -> StoryView:
        """Record a story view"""
        # Check if story is active and not expired
        if not story.is_active:
            raise ValidationError("Cannot view inactive story")
        
        if story.expires_at <= timezone.now():
            raise ValidationError("Story has expired")
        
        # Check if user is trying to view their own story (optional)
        if story.user == user:
            # Allow viewing own story but we might track it differently
            pass
        
        try:
            with transaction.atomic():
                # Use get_or_create to avoid duplicates (enforced by unique_together)
                view, created = StoryView.objects.get_or_create(
                    story=story,
                    user=user
                )
                return view
        except IntegrityError:
            # View already exists, return it
            return StoryView.objects.get(story=story, user=user)
    
    @staticmethod
    def has_viewed(story: Story, user: User) -> bool:
        """Check if user has viewed a story"""
        return StoryView.objects.filter(story=story, user=user).exists()
    
    @staticmethod
    def get_story_views(
        story: Story,
        limit: int = 100,
        offset: int = 0
    ) -> List[StoryView]:
        """Get all views for a specific story"""
        return list(
            StoryView.objects.filter(story=story)
            .select_related('user')
            .order_by('-viewed_at')[offset:offset + limit]
        )
    
    @staticmethod
    def get_user_viewed_stories(
        user: User,
        limit: int = 50,
        offset: int = 0
    ) -> List[StoryView]:
        """Get all stories viewed by a user"""
        return list(
            StoryView.objects.filter(user=user)
            .select_related('story', 'story__user')
            .order_by('-viewed_at')[offset:offset + limit]
        )
    
    @staticmethod
    def get_recent_viewers(
        story: Story,
        hours: int = 24,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent viewers of a story within specified hours"""
        time_threshold = timezone.now() - timezone.timedelta(hours=hours)
        
        views = StoryView.objects.filter(
            story=story,
            viewed_at__gte=time_threshold
        ).select_related('user').order_by('-viewed_at')[:limit]
        
        return [
            {
                'user': view.user,
                'viewed_at': view.viewed_at,
                'time_ago': timezone.now() - view.viewed_at
            }
            for view in views
        ]
    
    @staticmethod
    def get_story_view_count(story: Story) -> int:
        """Get total view count for a story"""
        return StoryView.objects.filter(story=story).count()
    
    @staticmethod
    def get_unique_viewers_count(story: Story) -> int:
        """Get count of unique viewers for a story"""
        return StoryView.objects.filter(story=story).values('user').distinct().count()
    
    @staticmethod
    def get_user_story_view_stats(user: User) -> Dict[str, Any]:
        """Get viewing statistics for a user"""
        # Stories viewed by user
        viewed_stories = StoryView.objects.filter(user=user)
        
        # Stories created by user and their views
        user_stories = Story.objects.filter(user=user)
        
        return {
            'stories_viewed_count': viewed_stories.count(),
            'unique_creators_viewed': viewed_stories.values('story__user').distinct().count(),
            'user_stories_view_count': sum(story.views.count() for story in user_stories),
            'recent_views': viewed_stories.filter(
                viewed_at__gte=timezone.now() - timezone.timedelta(hours=24)
            ).count()
        }
    
    @staticmethod
    def get_mutual_story_views(user1: User, user2: User) -> Dict[str, Any]:
        """Get mutual story viewing statistics between two users"""
        # Stories created by user1 that user2 has viewed
        user1_stories_viewed_by_user2 = StoryView.objects.filter(
            story__user=user1,
            user=user2
        ).count()
        
        # Stories created by user2 that user1 has viewed
        user2_stories_viewed_by_user1 = StoryView.objects.filter(
            story__user=user2,
            user=user1
        ).count()
        
        return {
            'user1_stories_viewed_by_user2': user1_stories_viewed_by_user2,
            'user2_stories_viewed_by_user1': user2_stories_viewed_by_user1,
            'total_mutual_views': user1_stories_viewed_by_user2 + user2_stories_viewed_by_user1
        }
    
    @staticmethod
    def cleanup_old_views(days: int = 90) -> int:
        """Delete view records older than specified days"""
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        old_views = StoryView.objects.filter(viewed_at__lt=time_threshold)
        count = old_views.count()
        old_views.delete()
        return count
    
    @staticmethod
    def get_popular_stories(
        hours: int = 24,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get most viewed stories within a time period"""
        from django.db.models import Count
        
        time_threshold = timezone.now() - timezone.timedelta(hours=hours)
        
        # Get stories with view counts
        stories = Story.objects.filter(
            is_active=True,
            expires_at__gt=timezone.now(),
            views__viewed_at__gte=time_threshold
        ).annotate(
            view_count=Count('views')
        ).filter(
            view_count__gt=0
        ).order_by('-view_count', '-created_at')[:limit]
        
        return [
            {
                'story': story,
                'view_count': story.view_count,
                'user': story.user
            }
            for story in stories
        ]