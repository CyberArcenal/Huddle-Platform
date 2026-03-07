# feed/state_transition_service/post.py (updated)

from feed.services import CommentService, LikeService
from feed.services.feed import FeedService
from feed.services.logging import log_post_deleted, log_post_restored
from notifications.services.notification import NotificationService


class PostStateTransitionService:
    """Handles side effects of post state changes."""

    @staticmethod
    def handle_is_deleted_change(post, old_value, new_value):
        if new_value is True:
            PostStateTransitionService._handle_post_deleted(post)
        elif new_value is False and old_value is True:
            PostStateTransitionService._handle_post_restored(post)

    @staticmethod
    def _handle_post_deleted(post):
        """Soft‑delete the post and all its related content."""
        # 1. Soft‑delete all comments on this post
        comments = post.comments.all()
        for comment in comments:
            CommentService.delete_comment(comment, soft=True)

        # 2. Delete all likes on this post (hard delete – no soft‑delete field)
        post.likes.all().delete()

        # 3. Remove from followers' feeds
        FeedService.remove_post_from_feeds(post)

        # 4. Optionally notify users who commented
        unique_commenters = set(comments.values_list("user_id", flat=True))
        for user_id in unique_commenters:
            NotificationService.send_post_deleted_notification(
                user_id=user_id, post=post
            )

        # 5. Log the deletion
        log_post_deleted(post)

    @staticmethod
    def _handle_post_restored(post):
        """Restore the post and its related content."""
        # 1. Restore comments (if they were soft‑deleted)
        for comment in post.comments.all():
            CommentService.restore_comment(comment)

        # 2. Likes are usually not restored (they were hard‑deleted)
        #    If you add soft‑delete to likes, restore them here.

        # 3. Re‑insert into followers' feeds
        FeedService.add_post_to_feeds(post)

        # 4. Log the restoration
        log_post_restored(post)
