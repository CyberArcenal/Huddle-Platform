# search/services/content_search.py
from typing import List, Dict, Any, Optional, Tuple

from django.db.models import Q

from feed.models.post import Post
from users.models import User
from groups.models import Group, GroupMember
from events.models import Event


class SearchService:
    """
    Service for searching content across the platform.
    """

    DEFAULT_ORDERING = {
        'users': '-date_joined',
        'groups': '-created_at',
        'events': '-start_time',
        'posts': '-created_at',
    }

    @classmethod
    def search_users(
        cls,
        query: str,
        requesting_user: Optional[User] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[User], int]:
        """
        Search users by username, email, or bio.
        Only active users (status active/restricted) are returned for non‑staff.
        """
        q = Q(username__icontains=query) | Q(email__icontains=query) | Q(bio__icontains=query)

        base_qs = User.objects.all()
        if not requesting_user or not requesting_user.is_staff:
            base_qs = base_qs.filter(is_active=True, status__in=['active', 'restricted'])

        qs = base_qs.filter(q).distinct()
        total = qs.count()
        results = qs.order_by(cls.DEFAULT_ORDERING['users'])[offset:offset + limit]
        return list(results), total

    @classmethod
    def search_groups(
        cls,
        query: str,
        requesting_user: Optional[User] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Group], int]:
        """
        Search groups by name or description with privacy rules:
        - public  → anyone
        - private → members only
        - secret  → members only
        """
        q = Q(name__icontains=query) | Q(description__icontains=query)

        if requesting_user and requesting_user.is_authenticated:
            member_group_ids = GroupMember.objects.filter(
                user=requesting_user
            ).values_list('group_id', flat=True)

            privacy_q = (
                Q(privacy='public') |
                (Q(privacy='private') & Q(id__in=member_group_ids)) |
                (Q(privacy='secret') & Q(id__in=member_group_ids))
            )
        else:
            privacy_q = Q(privacy='public')

        qs = Group.objects.filter(q).filter(privacy_q).distinct()
        total = qs.count()
        results = qs.order_by(cls.DEFAULT_ORDERING['groups'])[offset:offset + limit]
        return list(results), total

    @classmethod
    def search_events(
        cls,
        query: str,
        requesting_user: Optional[User] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Event], int]:
        """
        Search events by title or description.
        Visibility:
        - public          → anyone
        - private         → only the organizer (extend with invites later)
        - group events    → visible if user can see the group
        """
        q = Q(title__icontains=query) | Q(description__icontains=query)

        if requesting_user and requesting_user.is_authenticated:
            group_visible_ids = cls._get_visible_group_ids(requesting_user)

            visibility_q = (
                Q(event_type='public') |
                (Q(event_type='private') & Q(organizer=requesting_user)) |
                (Q(event_type='group') & Q(group_id__in=group_visible_ids))
            )
        else:
            group_public_ids = Group.objects.filter(privacy='public').values_list('id', flat=True)
            visibility_q = Q(event_type='public') | (Q(event_type='group') & Q(group_id__in=group_public_ids))

        qs = Event.objects.filter(q).filter(visibility_q).distinct()
        total = qs.count()
        results = qs.order_by(cls.DEFAULT_ORDERING['events'])[offset:offset + limit]
        return list(results), total

    @classmethod
    def search_posts(
        cls,
        query: str,
        requesting_user: Optional[User] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Post], int]:
        """
        Search posts by content.
        Privacy:
        - public    → anyone
        - followers → visible only to followers
        - secret    → never shown in search
        """
        q = Q(content__icontains=query) & Q(is_deleted=False)

        if requesting_user and requesting_user.is_authenticated:
            following_ids = requesting_user.following.values_list('following_id', flat=True)

            privacy_q = (
                Q(privacy='public') |
                (Q(privacy='followers') & Q(user_id__in=following_ids))
            )
        else:
            privacy_q = Q(privacy='public')

        qs = Post.objects.filter(q).filter(privacy_q).distinct()
        total = qs.count()
        results = qs.order_by(cls.DEFAULT_ORDERING['posts'])[offset:offset + limit]
        return list(results), total

    @classmethod
    def _get_visible_group_ids(cls, user: User) -> List[int]:
        """Return IDs of groups the user can see (public + all memberships)."""
        member_ids = GroupMember.objects.filter(user=user).values_list('group_id', flat=True)
        public_ids = Group.objects.filter(privacy='public').values_list('id', flat=True)
        return set(member_ids) | set(public_ids)