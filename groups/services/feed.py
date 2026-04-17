# group/services/group_content.py

import logging
from typing import List, Dict, Any, Optional

from django.db.models import Q, Prefetch
from feed.models import Post, Reel, Share
from feed.services.post import PostService
from feed.services.share import ShareService
from feed.services.reel import ReelService
from events.services.event import EventService
from groups.models import Group
from users.models import User

logger = logging.getLogger(__name__)


class GroupContentService:
    """
    Service to collect all content items belonging to a group,
    sorted by creation time, for use in a group feed.
    """

    @staticmethod
    def get_group_content(
        group: Group,
        requester: Optional[User] = None,
        max_items: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Return a list of dicts, each containing 'type' and 'item' for
        content items associated with the given group.
        Items are ordered by creation date (newest first) and limited to `max_items`.
        """
        items = []

        # 1. Posts in the group
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
            })

        # 2. Shares that have this group as the target
        #    (we assume Share has a 'group' field, set when sharing to a group)
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
            })

        # 3. Reels that belong to this group (if Reel has a 'group' field)
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
            })

        # 4. Events associated with the group (if Event has a 'group' field)
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
                'created_at': event.start_time,  # or created_at
            })

        # Sort all items by creation date (newest first)
        items.sort(key=lambda x: x['created_at'], reverse=True)

        # Limit to max_items
        return items[:max_items]