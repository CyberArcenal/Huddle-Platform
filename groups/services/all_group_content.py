# groups/services/all_group_content.py

import logging
from typing import List, Dict, Any, Optional

from feed.services.post import PostService
from feed.services.share import ShareService
from feed.services.reel import ReelService
from events.services.event import EventService
from groups.services.group import GroupService
from users.models import User

logger = logging.getLogger(__name__)


class AllGroupContentService:
    """
    Service to collect all content items belonging to all groups
    that a user can access, sorted by creation time.
    """

    @staticmethod
    def get_all_group_content(
        requester: Optional[User],
        max_items: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Return a list of dicts, each containing 'type' and 'item' for
        content items across all groups the requester can access.
        Items are ordered by creation date (newest first) and limited to `max_items`.
        """
        items: List[Dict[str, Any]] = []

        # Get all groups the user can see
        groups = GroupService.get_user_groups(user=requester)

        for group in groups:
            # 1. Posts
            posts = PostService.get_group_posts(
                group_id=group.id,
                user=requester,
                limit=max_items,
                offset=0,
            )
            for post in posts:
                items.append({
                    'type': 'post',
                    'item': post,
                    'created_at': post.created_at,
                    'group_id': group.id,
                })

            # 2. Shares
            shares = ShareService.get_group_shares(
                group=group,
                requester=requester,
                limit=max_items,
                offset=0,
            )
            for share in shares:
                items.append({
                    'type': 'share',
                    'item': share,
                    'created_at': share.created_at,
                    'group_id': group.id,
                })

            # 3. Reels
            reels = ReelService.get_group_reels(
                group=group,
                requester=requester,
                limit=max_items,
                offset=0,
            )
            for reel in reels:
                items.append({
                    'type': 'reel',
                    'item': reel,
                    'created_at': reel.created_at,
                    'group_id': group.id,
                })

            # 4. Events
            events = EventService.get_group_events(
                group=group,
                requester=requester,
                limit=max_items,
                offset=0,
            )
            for event in events:
                items.append({
                    'type': 'event',
                    'item': event,
                    'created_at': event.start_time,
                    'group_id': group.id,
                })

        # Sort all items by creation date (newest first)
        items.sort(key=lambda x: x['created_at'], reverse=True)

        # Limit to max_items
        return items[:max_items]
