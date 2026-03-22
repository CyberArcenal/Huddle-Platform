# feed/services/user_content.py
from typing import List, Dict, Any, Optional
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
        if method_name == 'get_user_posts':
            return PostService.get_user_posts(
                user_id=user.id, requester=requester, limit=limit, offset=0
            )
        if method_name == 'get_user_shares':
            return ShareService.get_user_shares(
                user=user, include_deleted=False, limit=limit, offset=0
            )
        if method_name == 'get_user_reels':
            return ReelService.get_user_reels(
                user=user, include_deleted=False, limit=limit, offset=0
            )
        if method_name == 'get_user_stories':
            return StoryService.get_user_stories(
                user=user, include_expired=False, limit=limit, offset=0
            )
        return []

    @classmethod
    def get_user_content(
        cls,
        user: User,
        requester: Optional[User],
        max_items: int = 500,
    ) -> List[Dict[str, Any]]:
        """Return merged list of all user content, sorted by created_at descending."""
        fetch_limit = max_items

        posts = cls._get_filtered_items('get_user_posts', user, requester, fetch_limit)
        shares = cls._get_filtered_items('get_user_shares', user, requester, fetch_limit)
        reels = cls._get_filtered_items('get_user_reels', user, requester, fetch_limit)
        stories = cls._get_filtered_items('get_user_stories', user, requester, fetch_limit)

        combined = []
        for item in posts:
            combined.append({'type': 'post', 'data': item, 'created_at': item.created_at, 'id': item.id})
        for item in shares:
            combined.append({'type': 'share', 'data': item, 'created_at': item.created_at, 'id': item.id})
        for item in reels:
            combined.append({'type': 'reel', 'data': item, 'created_at': item.created_at, 'id': item.id})
        for item in stories:
            combined.append({'type': 'story', 'data': item, 'created_at': item.created_at, 'id': item.id})

        combined.sort(key=lambda x: (-x['created_at'].timestamp(), -x['id']))
        return combined[:max_items]