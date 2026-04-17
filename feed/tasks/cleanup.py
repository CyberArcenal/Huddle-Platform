# feed/tasks/cleanup.py
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.db.models import Q

from feed.models.post import Post

logger = logging.getLogger(__name__)


@shared_task
def reset_stuck_processing_posts(minutes: int = 10) -> int:
    """
    Reset `processing=True` posts that have been stuck for longer than `minutes`.
    Returns the number of posts that were reset.
    """
    threshold = timezone.now() - timedelta(minutes=minutes)
    
    stuck_posts = Post.objects.filter(
        processing=True,
        created_at__lt=threshold
    )
    
    count = stuck_posts.count()
    if count == 0:
        logger.info("No stuck processing posts found.")
        return 0
    
    # Update in bulk for efficiency
    updated = stuck_posts.update(processing=False)
    
    # Log each post individually for debugging (optional)
    for post in stuck_posts.only('id'):
        logger.warning(f"Reset stuck processing flag for post {post.id} (created at {post.created_at})")
    
    logger.info(f"Reset {updated} stuck processing posts (older than {minutes} minutes).")
    return updated