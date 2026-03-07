from django.utils import timezone
from typing import List, Dict, Any

from stories.services.story import StoryService
from stories.services.story_view import StoryViewService
from ..models import Story, User
from users.services import UserFollowService


class StoryFeedService:
    """Service for story feed generation and management"""
    
    @staticmethod
    def generate_story_feed(
        user: User,
        include_own_stories: bool = True,
        limit_per_user: int = 3,
        max_users: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Generate a personalized story feed for a user
        
        Returns stories grouped by user, with recent stories from:
        1. Users followed by the current user
        2. Popular stories from non-followed users (optional)
        3. User's own stories (optional)
        """
        feed = []
        
        # 1. Get stories from followed users
        following_users = UserFollowService.get_following(user)
        
        for followed_user in following_users[:max_users]:
            user_stories = StoryService.get_user_stories(
                user=followed_user,
                include_expired=False,
                limit=limit_per_user
            )
            
            if user_stories:
                feed.append({
                    'user': followed_user,
                    'stories': user_stories,
                    'has_viewed_all': all(
                        StoryViewService.has_viewed(story, user)
                        for story in user_stories
                    ),
                    'type': 'following'
                })
        
        # 2. Add user's own stories if requested
        if include_own_stories:
            own_stories = StoryService.get_user_stories(
                user=user,
                include_expired=False,
                limit=limit_per_user
            )
            
            if own_stories:
                feed.insert(0, {  # Insert at beginning
                    'user': user,
                    'stories': own_stories,
                    'has_viewed_all': True,  # User has viewed their own stories
                    'type': 'own'
                })
        
        # 3. Add popular stories from non-followed users (discovery)
        # This can be expanded based on your discovery algorithm
        
        return feed
    
    @staticmethod
    def get_story_highlights(
        user: User,
        days: int = 7,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get story highlights (most viewed/liked stories)"""
        from django.db.models import Count, Q
        
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        # Get stories with highest view counts
        highlights = Story.objects.filter(
            user=user,
            created_at__gte=time_threshold,
            is_active=True
        ).annotate(
            view_count=Count('views')
        ).filter(
            view_count__gt=0
        ).order_by('-view_count', '-created_at')[:limit]
        
        return [
            {
                'story': story,
                'view_count': story.view_count,
                'engagement_rate': StoryFeedService.calculate_engagement_rate(story)
            }
            for story in highlights
        ]
    
    @staticmethod
    def calculate_engagement_rate(story: Story) -> float:
        """Calculate engagement rate for a story"""
        view_count = story.views.count()
        
        # If this is a user's story and we have follower count
        from users.services import UserFollowService
        follower_count = UserFollowService.get_follower_count(story.user)
        
        if follower_count > 0:
            return (view_count / follower_count) * 100
        
        return view_count  # Return absolute count if no followers
    
    @staticmethod
    def get_story_recommendations(
        user: User,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get story recommendations based on viewing history"""
        # Get users whose stories the current user has viewed
        viewed_stories = StoryViewService.get_user_viewed_stories(user, limit=100)
        
        if not viewed_stories:
            # If no viewing history, return popular stories
            return StoryViewService.get_popular_stories(limit=limit)
        
        # Extract creators from viewed stories
        creators = set(view.story.user for view in viewed_stories)
        
        # Exclude users already followed and self
        from users.services import UserFollowService
        following_users = set(UserFollowService.get_following(user))
        creators_to_explore = creators - following_users - {user}
        
        # Get recent stories from these creators
        recommendations = []
        for creator in list(creators_to_explore)[:limit]:
            creator_stories = StoryService.get_user_stories(
                user=creator,
                include_expired=False,
                limit=1  # Get most recent story
            )
            
            if creator_stories:
                recommendations.append({
                    'user': creator,
                    'latest_story': creator_stories[0],
                    'reason': 'Viewed similar content'
                })
        
        return recommendations
    
    @staticmethod
    def remove_story_from_feeds(story: Story):
        """Remove story from all users' feeds (e.g., from cache)."""
        # Example: if using Redis sorted sets per user, remove this story
        # from the feed of every follower.
        print(f"Removing story {story.id} from feeds.")

    @staticmethod
    def add_story_to_feeds(story: Story):
        """Add story back to followers' feeds (after reactivation)."""
        print(f"Adding story {story.id} to feeds.")