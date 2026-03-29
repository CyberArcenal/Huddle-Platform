# feed/services/user_content.py
from typing import List, Dict, Any, Optional
from feed.services.view import ViewService
from users.models import User
from feed.services.post import PostService
from feed.services.share import ShareService
from feed.services.reel import ReelService
from stories.services.story import StoryService


class UserContentService:
    FETCH_LIMIT_PER_TYPE = 500  # enough for profile feeds

    @classmethod
    def _get_filtered_items(
        cls,
        method_name: str,
        user: User,
        requester: Optional[User],
        limit: int,
    ) -> List[Any]:
        """Fetch items from a specific content type with privacy filtering."""
        if method_name == "get_user_posts":
            return PostService.get_user_posts(
                user=user, requester=requester, limit=limit, offset=0
            )
        if method_name == "get_user_shares":
            return ShareService.get_user_shares(
                user=user, include_deleted=False, limit=limit, offset=0
            )
        if method_name == "get_user_reels":
            return ReelService.get_user_reels(
                user=user, include_deleted=False, limit=limit, offset=0
            )
        if method_name == "get_user_stories":
            return StoryService.get_user_stories(
                user=user, include_expired=False, limit=limit, offset=0
            )
        return []

    @classmethod
    def _get_user_images(
        cls, user: User, requester: Optional[User], limit: int
    ) -> List[Dict[str, Any]]:
        from users.services.user_image import UserImageService

        images = UserImageService.get_visible_images(user, requester, limit)
        result = []
        for img in images:
            result.append(
                {
                    "type": "user_image",
                    "item": img,
                    "created_at": img.created_at,
                    "id": img.id,
                }
            )
        return result

    @classmethod
    def get_user_content(
        cls,
        user: User,
        requester: Optional[User],
        max_items: int = 500,
    ) -> List[Dict[str, Any]]:
        """Return merged list of all user content, sorted by created_at descending."""
        fetch_limit = max_items

        posts = cls._get_filtered_items("get_user_posts", user, requester, fetch_limit)
        shares = cls._get_filtered_items(
            "get_user_shares", user, requester, fetch_limit
        )
        reels = cls._get_filtered_items("get_user_reels", user, requester, fetch_limit)
        stories = StoryService.get_user_stories(
            user=user, include_expired=False, limit=20  # enough for a story ring
        )
        user_images = cls._get_user_images(user, requester, fetch_limit)

        combined = []
        for item in posts:
            combined.append(
                {
                    "type": "post",
                    "item": item,
                    "created_at": item.created_at,
                    "id": item.id,
                }
            )
        for item in shares:
            combined.append(
                {
                    "type": "share",
                    "item": item,
                    "created_at": item.created_at,
                    "id": item.id,
                }
            )
        for item in reels:
            combined.append(
                {
                    "type": "reel",
                    "item": item,
                    "created_at": item.created_at,
                    "id": item.id,
                }
            )
        # --- Group stories into a single row ---
        if stories:
            comb = group_user_story(user, stories, requester)
            combined.append(comb)
        # ---------------------------------------
        for item in user_images:
            combined.append(item)

        combined.sort(key=lambda x: (-x['created_at'].timestamp(), -int(str(x['id']).split('_')[-1]) if x['id'] else 0))
        return combined[:max_items]


def group_user_story(
    user: User, stories: List[Any], requester: Optional[User]
) -> Dict[str, Any]:
    """Helper to group a user's stories into a single feed item."""
    latest_created = max(story.created_at for story in stories)
    return {
            'type': 'user_story',
            'item': {
                'user': user,
                'stories': stories,
                'has_viewed_all': (requester == user),   # True if owner
                'type': 'own' if requester == user else 'following',
                'stories_count': len(stories),
            },
            'created_at': latest_created,
            'id': f'user_story_{user.id}',
        }
