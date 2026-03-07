from stories.services.story_view import StoryViewService
from stories.services.story_feed import StoryFeedService
from analytics.services.platform_analytics import PlatformAnalyticsService
# If you have a dedicated story analytics service, import it here


class StoryStateTransitionService:
    """Handles side effects of story state changes."""

    @staticmethod
    def handle_is_active_change(story, old_value, new_value):
        """Called when story.is_active changes."""
        if new_value is False:
            # Story was deactivated (expired or manually deactivated)
            StoryStateTransitionService._handle_story_deactivated(story)
        elif new_value is True and old_value is False:
            # Story was reactivated (if allowed)
            StoryStateTransitionService._handle_story_reactivated(story)

    @staticmethod
    def _handle_story_deactivated(story):
        """Story became inactive – clean up views, remove from feeds, update analytics."""
        # 1. Delete all view records for this story (or mark them as inactive)
        deleted_views = StoryViewService.clear_story_views(story)

        # 2. Remove story from all feeds (e.g., story feed cache)
        StoryFeedService.remove_story_from_feeds(story)

        # 3. Update platform analytics (decrement active stories count, etc.)
        PlatformAnalyticsService.decrement_active_stories()

        # Optional: log the deactivation for audit
        if hasattr(story, 'log_events'):
            from stories.services.logging import log_story_deactivated
            log_story_deactivated(story, views_deleted=deleted_views)

    @staticmethod
    def _handle_story_reactivated(story):
        """Story was manually reactivated (if such operation is allowed)."""
        # 1. Views are usually not restored; they were deleted.
        # 2. Re‑insert story into feeds
        StoryFeedService.add_story_to_feeds(story)

        # 3. Update analytics
        PlatformAnalyticsService.increment_active_stories()

        # Optional: log reactivation
        if hasattr(story, 'log_events'):
            from stories.services.logging import log_story_reactivated
            log_story_reactivated(story)