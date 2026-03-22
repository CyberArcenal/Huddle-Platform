from typing import List, Dict, Any, Tuple
from django.db import models
from django.db.models import Q
from users.models import User
from feed.models import PostMedia, Reel
from stories.models import Story


class UserMediaService:
    """
    Service to gather all media items (post images/videos, reels, story media)
    from a user, sorted by creation date, for a media grid.
    """

    @classmethod
    def get_user_media(
        cls, user: User, page: int = 1, page_size: int = 20, max_items: int = 500
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Return a list of media items (each as a dict) from the user,
        sorted by created_at descending, along with the total count.
        Uses simple page-based pagination.
        """
        offset = (page - 1) * page_size

        # Fetch all media items from all sources (up to max_items)
        # 1. Post media
        post_media_qs = PostMedia.objects.filter(
            post__user=user, post__is_deleted=False
        ).select_related("post").order_by("-post__created_at", "order")
        post_media = list(post_media_qs[:max_items])

        # 2. Reels
        reels = list(
            Reel.objects.filter(user=user, is_deleted=False)
            .order_by("-created_at")[:max_items]
        )

        # 3. Story media (image/video stories that are active and not expired)
        stories = list(
            Story.objects.filter(
                user=user,
                is_active=True,
                expires_at__gt=models.F("expires_at"),  # not expired
                story_type__in=["image", "video"],
            )
            .order_by("-created_at")[:max_items]
        )

        # Build combined list
        combined = []

        for media in post_media:
            combined.append(
                {
                    "type": "post_media",
                    "url": media.file.url if media.file else None,
                    "thumbnail": None,  # posts may not have separate thumbnails
                    "created_at": media.post.created_at,
                    "content_id": media.post.id,
                    "content_type": "post",
                    "media_order": media.order,
                    "media_id": media.id,
                }
            )

        for reel in reels:
            combined.append(
                {
                    "type": "reel",
                    "url": reel.video.url if reel.video else None,
                    "thumbnail": reel.thumbnail.url if reel.thumbnail else None,
                    "created_at": reel.created_at,
                    "content_id": reel.id,
                    "content_type": "reel",
                    "media_order": None,
                }
            )

        for story in stories:
            combined.append(
                {
                    "type": "story_media",
                    "url": story.media_url.url if story.media_url else None,
                    "thumbnail": None,
                    "created_at": story.created_at,
                    "content_id": story.id,
                    "content_type": "story",
                    "media_order": None,
                }
            )

        # Sort by created_at descending
        combined.sort(key=lambda x: x["created_at"], reverse=True)

        total = len(combined)
        paginated = combined[offset : offset + page_size]

        return paginated, total