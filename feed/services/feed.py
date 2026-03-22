# feed/services/feed.py

import logging
from typing import List, Dict, Any, Optional
from events.services.event import EventService
from users.models import User
from feed.services.post import PostService
from feed.services.reel import ReelService
from feed.services.share import ShareService
from stories.services.story_feed import StoryFeedService
from users.services.matching import MatchingService
from groups.services.group_suggestion import GroupSuggestionService
from groups.services.group import GroupService  # for group posts

logger = logging.getLogger(__name__)

import inspect
from typing import Callable





class FeedService:
    """
    Service for building personalized feeds as rows of different content types.

    Behavior:
    - The feed is paginated by "rows" (slots). Each page contains `page_size` slots.
    - The posts and shares rows each occupy one slot but return multiple items (preview).
    - Curated rows (reels, stories, suggested_users, match_users, recommended_groups, events)
      each occupy one slot and return a small preview list.
    - posts_preview and shares_preview control how many items are returned inside the posts/shares rows.
    - post_offset and share_offset are computed from page and preview sizes to avoid duplication across pages.
    - Each posts/shares row includes a `pagination` dict: {"next_offset", "has_more", "limit"}.
    """

    # Curated rows only (fixed count)
    ROW_CONFIG = {
        "reels": {"limit": 10, "service": ReelService.get_feed_reels},
        "stories": {"limit": 10, "service": StoryFeedService.generate_story_feed},
        "suggested_users": {
            "limit": 10,
            "service": MatchingService.get_suggested_users,
        },
        "match_users": {"limit": 10, "service": MatchingService.get_matches},
        "recommended_groups": {
            "limit": 10,
            "service": GroupSuggestionService.get_ranked_recommendations,
        },
        "events": {"limit": 10, "service": EventService.get_recommended_events},
        "group_posts": {
            "limit": 10,
            "service": GroupService.get_user_group_posts,
        },  # new for groups tab
        "following_posts": {
            "limit": 10,
            "service": PostService.get_following_posts,
        },  # new for following tab
        "friends_posts": {
            "limit": 10,
            "service": PostService.get_friend_posts,
        },  # new for friends tab
    }

    # Defaults for previews
    DEFAULT_POSTS_PREVIEW = 5
    DEFAULT_SHARES_PREVIEW = 2
    CURATED_PREVIEW = 6  # preview size for curated rows

    # Dedicated filler rows
    @classmethod
    def get_feed_posts(cls, user: User, limit: int = 20, offset: int = 0):
        return PostService.get_feed_posts(user, limit=limit, offset=offset)

    @classmethod
    def get_feed_shares(cls, user: User, limit: int = 20, offset: int = 0):
        return ShareService.get_feed_shares(user, limit=limit, offset=offset)
    
    # helper: call a service with limit if supported, otherwise call without it
    @classmethod
    def _call_service_with_limit(cls, service: Callable, user, limit: int):
        """
        Try to call service(user, limit=limit). If the service signature
        doesn't accept 'limit', call service(user) instead. If service expects
        positional args, try service(user, limit).
        """
        try:
            sig = inspect.signature(service)
            params = sig.parameters

            # If service accepts 'limit' as a parameter name, call with keyword
            if "limit" in params:
                return service(user, limit=limit)

            # If service accepts a second positional parameter, call positionally
            # (first param is assumed to be 'user')
            if len(params) >= 2:
                return service(user, limit)

            # Otherwise, call with only user
            return service(user)
        except (TypeError, ValueError):
            # Fallback: try calling with keyword, then without
            try:
                return service(user, limit=limit)
            except TypeError:
                return service(user)

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
        Build feed rows for the given page.

        - page: 1-based page number for row slots
        - page_size: number of row slots per page
        - posts_preview: number of posts to include inside the posts row
        - shares_preview: number of shares to include inside the shares row
        - include_types: optional list to restrict curated row types
        - feed_type: controls which curated rows are considered and titles
        """

        # Determine which rows to include based on feed_type
        if feed_type == "home":
            # Default: posts, shares, and all curated rows except group_posts
            curated_types = [
                t
                for t in cls.ROW_CONFIG.keys()
                if t not in ("group_posts", "following_posts", "friends_posts")
            ]
            include_posts_row = True
            include_shares_row = True
        elif feed_type == "discover":
            curated_types = ["suggested_users", "match_users", "events", "reels"]
            include_posts_row = False
            include_shares_row = False
        elif feed_type == "friends":
            curated_types = (
                []
            )  # no curated rows for friends tab (only posts from friends)
            include_posts_row = False
            include_shares_row = False
            # We'll add a dedicated friends_posts row below
        elif feed_type == "following":
            curated_types = []
            include_posts_row = False
            include_shares_row = False
            # We'll add a dedicated following_posts row below
        elif feed_type == "groups":
            curated_types = ["recommended_groups", "events"]  # optionally include these
            include_posts_row = False
            include_shares_row = False
            # We'll add a dedicated group_posts row below
        elif feed_type == "stories":
            curated_types = ["stories"]
            include_posts_row = False
            include_shares_row = False
        else:
            curated_types = []
            include_posts_row = True
            include_shares_row = True

        # Compute offsets for posts/shares if they are included
        post_offset = (page - 1) * posts_preview if include_posts_row else 0
        share_offset = (page - 1) * shares_preview if include_shares_row else 0

        rows: List[Dict[str, Any]] = []
        slots_left = page_size

        # 1) Posts row (if enabled)
        if include_posts_row:
            try:
                posts = cls.get_feed_posts(
                    user, limit=posts_preview, offset=post_offset
                )
            except Exception as e:
                logger.exception("Error fetching posts preview: %s", e)
                posts = []
            if posts:
                fetched = len(posts)
                has_more = fetched == posts_preview
                rows.append(
                    {
                        "row_type": "posts",
                        "items": posts,
                        "title": cls._get_row_title("posts", feed_type),
                        "pagination": {
                            "next_offset": post_offset + fetched,
                            "has_more": has_more,
                            "limit": posts_preview,
                        },
                    }
                )
                slots_left -= 1

        # 2) Shares row (if enabled)
        if include_shares_row and slots_left > 0:
            try:
                shares = cls.get_feed_shares(
                    user, limit=shares_preview, offset=share_offset
                )
            except Exception as e:
                logger.exception("Error fetching shares preview: %s", e)
                shares = []
            if shares:
                fetched = len(shares)
                has_more = fetched == shares_preview
                rows.append(
                    {
                        "row_type": "shares",
                        "items": shares,
                        "title": cls._get_row_title("shares", feed_type),
                        "pagination": {
                            "next_offset": share_offset + fetched,
                            "has_more": has_more,
                            "limit": shares_preview,
                        },
                    }
                )
                slots_left -= 1

        # 3) Special rows for friends/following/groups tabs (dedicated posts rows)
        if feed_type == "friends" and slots_left > 0:
            try:
                friends_posts = cls.ROW_CONFIG["friends_posts"]["service"](
                    user, limit=posts_preview
                )
            except Exception as e:
                logger.exception("Error fetching friends posts: %s", e)
                friends_posts = []
            if friends_posts:
                rows.append(
                    {
                        "row_type": "friends_posts",
                        "items": friends_posts,
                        "title": cls._get_row_title("friends_posts", feed_type),
                        "pagination": None,
                    }
                )
                slots_left -= 1

        if feed_type == "following" and slots_left > 0:
            try:
                following_posts = cls.ROW_CONFIG["following_posts"]["service"](
                    user, limit=posts_preview
                )
            except Exception as e:
                logger.exception("Error fetching following posts: %s", e)
                following_posts = []
            if following_posts:
                rows.append(
                    {
                        "row_type": "following_posts",
                        "items": following_posts,
                        "title": cls._get_row_title("following_posts", feed_type),
                        "pagination": None,
                    }
                )
                slots_left -= 1

        if feed_type == "groups" and slots_left > 0:
            try:
                group_posts = cls.ROW_CONFIG["group_posts"]["service"](
                    user, limit=posts_preview
                )
            except Exception as e:
                logger.exception("Error fetching group posts: %s", e)
                group_posts = []
            if group_posts:
                rows.append(
                    {
                        "row_type": "group_posts",
                        "items": group_posts,
                        "title": cls._get_row_title("group_posts", feed_type),
                        "pagination": None,
                    }
                )
                slots_left -= 1

        # 4) Fill remaining slots with curated rows
        for row_type in curated_types:
            if slots_left <= 0:
                break
            if row_type in (
                "posts",
                "shares",
                "group_posts",
                "following_posts",
                "friends_posts",
            ):
                continue  # already handled or not a curated row
            config = cls.ROW_CONFIG[row_type]
            try:
                # Use helper to call service safely with/without limit
                service = config["service"]
                service_limit = min(
                    config.get("limit", cls.CURATED_PREVIEW), cls.CURATED_PREVIEW
                )
                items = FeedService._call_service_with_limit(service, user, service_limit)
            except Exception as e:
                logger.exception("Error fetching %s: %s", row_type, e)
                continue
            if not items:
                continue
            rows.append(
                {
                    "row_type": row_type,
                    "items": items,
                    "title": cls._get_row_title(row_type, feed_type),
                    "pagination": None,
                }
            )
            slots_left -= 1

        return rows

    @staticmethod
    def _get_row_title(row_type: str, feed_type: str) -> str:
        # default titles
        titles = {
            "reels": "Reels you might like",
            "stories": "Stories from people you follow",
            "suggested_users": "People you may know",
            "match_users": "Your best matches",
            "recommended_groups": "Recommended groups",
            "events": "Upcoming events you may join",
            "posts": "Posts from people you follow",
            "shares": "Shared posts from your network",
            "group_posts": "Posts from your groups",
            "following_posts": "Posts from people you follow",
            "friends_posts": "Posts from your friends",
        }

        # override titles based on feed_type
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
                "group_posts": "Latest group posts",
            }
            return overrides.get(row_type, titles.get(row_type, ""))

        if feed_type == "friends":
            return titles.get("friends_posts", "Posts from friends")

        if feed_type == "following":
            return titles.get("following_posts", "Posts from people you follow")

        if feed_type == "stories":
            return "Latest stories"

        # default (home feed)
        return titles.get(row_type, "")
