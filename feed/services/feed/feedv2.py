# feed/services/feed.py (refactored v2 with single row per home page)

import logging
import random
from typing import List, Dict, Any, Optional

from events.services.event import EventService
from users.models import User
from feed.services.post import PostService
from feed.services.reel import ReelService
from feed.services.share import ShareService
from stories.services.story_feed import StoryFeedService
from dating.services.matching import MatchingService
from groups.services.group_suggestion import GroupSuggestionService

logger = logging.getLogger(__name__)


class FeedService:
    """
    Service for building a unified feed as a list of items/rows.

    BEHAVIOR (UPDATED for home feed):
    - Posts and shares are always returned as SINGLE items (type='post' or 'share').
    - Curated content (reels, stories, suggested_users, match_users,
      recommended_groups, events) is returned as ROWS.
    - For feed_type="home":
        * Returns a list where each page contains:
          - Many single post/share items (paginated)
          - EXACTLY ONE curated row (randomly selected)
        * Total entries per page = page_size (including the row).
    - For other feed types: returns mixed list of items + rows,
      paginated by total entries (page_size).
    - Removed unsupported row types (group_posts, following_posts, friends_posts).
    """

    # Curated rows only – types that have a serializer in ROW_TYPE_SERIALIZER
    CURATED_SERVICES = {
        "reels": {
            "limit": 10,
            "service": ReelService.get_feed_reels,
            "category": "media",
        },
        "stories": {
            "limit": 10,
            "service": StoryFeedService.get_story_feed_items,
            "category": "media",
        },
        "suggested_users": {
            "limit": 10,
            "service": MatchingService.get_suggested_users,
            "category": "user_match",
        },
        "match_users": {
            "limit": 10,
            "service": MatchingService.get_matches,
            "category": "user_match",
        },
        "recommended_groups": {
            "limit": 10,
            "service": GroupSuggestionService.get_ranked_recommendations,
            "category": "group",
        },
        "events": {
            "limit": 10,
            "service": EventService.get_recommended_events,
            "category": "event",
        },
    }

    DEFAULT_POSTS_PREVIEW = 5   # base fetch size for posts
    DEFAULT_SHARES_PREVIEW = 2  # base fetch size for shares
    CURATED_PREVIEW = 6         # preview size for curated rows

    # Position where the single row appears in the home feed (0 = first, -1 = last)
    HOME_ROW_POSITION = 3   # e.g., after the first 3 items

    @classmethod
    def get_feed_posts(cls, user: User, limit: int = 20, offset: int = 0):
        return PostService.get_feed_posts(user, limit=limit, offset=offset)

    @classmethod
    def get_feed_shares(cls, user: User, limit: int = 20, offset: int = 0):
        return ShareService.get_feed_shares(user, limit=limit, offset=offset)
    
    @classmethod
    def get_feed_rows(
        cls,
        user: User,
        page: int = 1,
        page_size: int = 10,
        posts_preview: int = DEFAULT_POSTS_PREVIEW,
        shares_preview: int = DEFAULT_SHARES_PREVIEW,
        include_types: Optional[List[str]] = None,
        feed_type: str = "home",
    ) -> List[Dict[str, Any]]:
        """
        Build a paginated feed list.
        """
        # ------------------------------------------------------------------
        # HOME FEED: single items (posts/shares) + exactly ONE curated row
        # ------------------------------------------------------------------
        if feed_type == "home":
            # Fetch enough posts and shares to cover the page (excluding the row)
            # We need (page_size - 1) items because one slot is taken by the row.
            items_needed = page_size - 1
            if items_needed < 0:
                items_needed = 0

            # Fetch more than needed to allow shuffling and avoid empty pages
            fetch_limit = max((page * items_needed) + 10, posts_preview * 2)
            posts = cls.get_feed_posts(user, limit=fetch_limit, offset=0)
            shares = cls.get_feed_shares(user, limit=fetch_limit, offset=0)

            # Build flat list of single items
            all_items = []
            for post in posts:
                all_items.append({"type": "post", "item": post})
            for share in shares:
                all_items.append({"type": "share", "item": share})

            random.shuffle(all_items)

            # Paginate the items (without the row first)
            start_idx = (page - 1) * items_needed
            end_idx = start_idx + items_needed
            page_items = all_items[start_idx:end_idx]

            # Now select exactly ONE curated row for this page
            curated_row = cls._get_one_curated_row(user, feed_type)
            if curated_row:
                # Insert the row at the configured position (clamp to list length)
                pos = min(cls.HOME_ROW_POSITION, len(page_items))
                page_items.insert(pos, curated_row)
            else:
                # If no row available, fill with more items? Keep as is.
                pass

            return page_items

        # ------------------------------------------------------------------
        # OTHER FEED TYPES (discover, friends, following, groups, stories, etc.)
        # ------------------------------------------------------------------
        # Determine which curated rows to include (only those in CURATED_SERVICES)
        if feed_type == "discover":
            curated_types = ["suggested_users", "match_users", "events", "reels"]
            include_posts = False
            include_shares = False
        elif feed_type == "friends":
            curated_types = []
            include_posts = False
            include_shares = False
        elif feed_type == "following":
            curated_types = []
            include_posts = False
            include_shares = False
        elif feed_type == "groups":
            curated_types = ["recommended_groups", "events"]
            include_posts = False
            include_shares = False
        elif feed_type == "stories":
            curated_types = ["stories"]
            include_posts = False
            include_shares = False
        else:  # default fallback
            curated_types = list(cls.CURATED_SERVICES.keys())
            include_posts = True
            include_shares = True

        entries = []

        def has_items(data):
            if data is None:
                return False
            try:
                return len(data) > 0
            except TypeError:
                return bool(data)

        # 1) Single post items
        if include_posts:
            post_offset = (page - 1) * posts_preview
            try:
                posts = cls.get_feed_posts(user, limit=posts_preview, offset=post_offset)
            except Exception as e:
                logger.exception("Error fetching posts: %s", e)
                posts = []
            for post in posts:
                entries.append({"type": "post", "item": post})

        # 2) Single share items
        if include_shares:
            share_offset = (page - 1) * shares_preview
            try:
                shares = cls.get_feed_shares(user, limit=shares_preview, offset=share_offset)
            except Exception as e:
                logger.exception("Error fetching shares: %s", e)
                shares = []
            for share in shares:
                entries.append({"type": "share", "item": share})

        # 3) Special feed types: friends, following, groups (as single posts)
        if feed_type == "friends":
            try:
                friends_posts = PostService.get_friend_posts(user, limit=posts_preview)
            except Exception as e:
                logger.exception("Error fetching friends posts: %s", e)
                friends_posts = []
            for post in friends_posts:
                entries.append({"type": "post", "item": post})

        if feed_type == "following":
            try:
                following_posts = PostService.get_following_posts(user, limit=posts_preview)
            except Exception as e:
                logger.exception("Error fetching following posts: %s", e)
                following_posts = []
            for post in following_posts:
                entries.append({"type": "post", "item": post})

        if feed_type == "groups":
            try:
                # Note: GroupService.get_user_group_posts is imported but not in CURATED_SERVICES
                from groups.services.group import GroupService
                group_posts = GroupService.get_user_group_posts(user, limit=posts_preview)
            except Exception as e:
                logger.exception("Error fetching group posts: %s", e)
                group_posts = []
            for post in group_posts:
                entries.append({"type": "post", "item": post})

        # 4) Curated rows (multiple rows allowed for non-home feeds)
        added_user_match = False
        for row_type in curated_types:
            if row_type not in cls.CURATED_SERVICES:
                continue
            config = cls.CURATED_SERVICES[row_type]
            category = config.get("category")
            if category == "user_match" and added_user_match:
                continue

            service = config["service"]
            service_limit = min(config.get("limit", cls.CURATED_PREVIEW), cls.CURATED_PREVIEW)
            try:
                items = cls._call_service_with_limit(service, user, service_limit)
            except Exception as e:
                logger.exception("Error fetching %s: %s", row_type, e)
                continue

            if has_items(items):
                entries.append({
                    "row_type": row_type,
                    "items": items,
                    "title": cls._get_row_title(row_type, feed_type),
                    "pagination": None,
                })
                if category == "user_match":
                    added_user_match = True

        # Paginate entries by page_size
        start = (page - 1) * page_size
        end = start + page_size
        return entries[start:end]

    @classmethod
    def _get_one_curated_row(cls, user: User, feed_type: str) -> Optional[Dict[str, Any]]:
        """
        Randomly select one curated row type (with available items) and return it.
        Avoids user_match duplication by only returning one user-match row if selected.
        """
        # List of all curated row types (excluding any that might be empty)
        available_types = list(cls.CURATED_SERVICES.keys())
        if not available_types:
            return None

        # Shuffle to get a random order
        random.shuffle(available_types)

        added_user_match = False
        for row_type in available_types:
            config = cls.CURATED_SERVICES[row_type]
            category = config.get("category")
            if category == "user_match" and added_user_match:
                continue

            service = config["service"]
            service_limit = min(config.get("limit", cls.CURATED_PREVIEW), cls.CURATED_PREVIEW)
            try:
                items = cls._call_service_with_limit(service, user, service_limit)
            except Exception as e:
                logger.exception("Error fetching %s for home row: %s", row_type, e)
                continue

            if items and len(items) > 0:
                return {
                    "row_type": row_type,
                    "items": items,
                    "title": cls._get_row_title(row_type, feed_type),
                    "pagination": None,
                }
        return None

    @classmethod
    def _call_service_with_limit(cls, service, user, limit):
        import inspect
        try:
            sig = inspect.signature(service)
            if "limit" in sig.parameters:
                return service(user, limit=limit)
            if len(sig.parameters) >= 2:
                return service(user, limit)
            return service(user)
        except Exception:
            try:
                return service(user, limit=limit)
            except TypeError:
                return service(user)

    @staticmethod
    def _get_row_title(row_type: str, feed_type: str) -> str:
        titles = {
            "reels": "Reels you might like",
            "stories": "Stories from people you follow",
            "suggested_users": "People you may know",
            "match_users": "Your best matches",
            "recommended_groups": "Recommended groups",
            "events": "Upcoming events you may join",
        }

        if feed_type == "discover":
            overrides = {
                "reels": "Trending reels",
                "suggested_users": "Discover new people",
                "match_users": "Potential matches",
                "events": "Events you might be interested in",
            }
            return overrides.get(row_type, titles.get(row_type, ""))

        if feed_type == "groups":
            overrides = {
                "recommended_groups": "Groups you may want to join",
                "events": "Group events happening soon",
            }
            return overrides.get(row_type, titles.get(row_type, ""))

        if feed_type == "stories":
            return "Latest stories"

        # home feed title (can be customized)
        return titles.get(row_type, "")

    @classmethod
    def remove_post_from_feeds(cls, post):
        """
        Invalidate or remove a post from any pre‑computed feed caches.
        Currently a placeholder because feeds are built dynamically.
        """
        # Example: delete from a Redis feed list
        # from django.core.cache import cache
        # cache.delete_pattern(f"feed:*:{post.id}")
        logger.info(f"Post {post.id} removed from feeds (cache invalidation)")

    @classmethod
    def add_post_to_feeds(cls, post):
        """
        Re‑insert a restored post into followers' feeds.
        Placeholder – dynamic feeds will include it automatically.
        """
        logger.info(f"Post {post.id} restored – will appear in feeds on next query")