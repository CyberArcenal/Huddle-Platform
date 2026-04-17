# feed/state_transition_service/post.py (fixed)

import logging
from django.contrib.contenttypes.models import ContentType
from feed.models.comment import Comment
from feed.services.comment import CommentService
from feed.services.feed.feedv2 import FeedService
from notifications.services.notification_queue import NotificationQueueService

logger = logging.getLogger(__name__)

def log_post_deleted(post):
    logger.info(f"Post {post.id} by user {post.user_id} was soft-deleted")

def log_post_restored(post):
    logger.info(f"Post {post.id} by user {post.user_id} was restored")


class PostStateTransitionService:
    """Handles side effects of post state changes (soft-delete / restore)."""

    @staticmethod
    def handle_is_deleted_change(post, old_value, new_value):
        if new_value is True:
            PostStateTransitionService._handle_post_deleted(post)
        elif new_value is False and old_value is True:
            PostStateTransitionService._handle_post_restored(post)

    @staticmethod
    def _handle_post_deleted(post):
        """Soft‑delete the post and all its related content."""
        # 1. Get content type for Post model
        post_ct = ContentType.objects.get_for_model(post)

        # 2. Get all comments on this post (generic relation)
        comments = Comment.objects.filter(
            content_type=post_ct,
            object_id=post.id
        )

        # 3. Soft‑delete each comment
        for comment in comments:
            CommentService.soft_delete_comment(comment)   # implement if missing

        # 4. Hard‑delete all likes on this post (likes are generic too)
        from feed.models.reaction import Reaction
        Reaction.objects.filter(
            content_type=post_ct,
            object_id=post.id
        ).delete()

        # 5. Remove from followers' feeds (cache invalidation / placeholder)
        FeedService.remove_post_from_feeds(post)

        # 6. Notify users who commented
        unique_commenter_ids = set(comments.values_list("user_id", flat=True))
        for user_id in unique_commenter_ids:
            NotificationQueueService.queue_notification(
                channel="push",
                recipient=str(user_id),
                subject="Post deleted",
                message=f"The post you commented on has been deleted by the author.",
                metadata={"post_id": post.id, "post_author": post.user_id}
            )

        # 7. Log deletion
        log_post_deleted(post)

    @staticmethod
    def _handle_post_restored(post):
        """Restore the post and its related content."""
        post_ct = ContentType.objects.get_for_model(post)

        # 1. Restore comments (if they were soft‑deleted)
        comments = Comment.objects.filter(
            content_type=post_ct,
            object_id=post.id
        )
        for comment in comments:
            CommentService.restore_comment(comment)

        # 2. Likes are hard‑deleted, so not restored.

        # 3. Re‑insert into followers' feeds
        FeedService.add_post_to_feeds(post)

        # 4. Log restoration
        log_post_restored(post)