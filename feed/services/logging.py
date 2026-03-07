import logging

logger = logging.getLogger(__name__)


def log_post_deleted(post):
    """Log that a post was soft-deleted."""
    logger.info(f"Post {post.id} by user {post.user_id} soft-deleted at {post.updated_at}")


def log_post_restored(post):
    """Log that a post was restored."""
    logger.info(f"Post {post.id} by user {post.user_id} restored at {post.updated_at}")