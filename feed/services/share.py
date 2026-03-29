from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.contrib.contenttypes.models import ContentType
from typing import Optional, List, Dict, Any, Union
from django.db.models import Q, Prefetch

from feed.models.media import Media
from feed.models.post import Post
from groups.models.group import Group
from users.models import User
from users.services.user_follow import UserFollowService
from ..models import Share


class ShareService:
    """Service for Share model operations."""

    @staticmethod
    def create_share(
        user: User,
        content_object,
        caption: str = "",
        privacy: str = "public",
        group: Group = None,
    ) -> Share:
        """
        Create a new share for any content object.
        """
        if not user or not content_object:
            raise ValidationError("User and content object are required.")

        if group and not isinstance(group, Group):
            raise ValidationError(f"Group: {group} is not an instance")

        if not isinstance(user, User):
            raise ValidationError(f"User: {user} is not and intance")

        # Validate privacy
        valid_privacy = [
            choice[0] for choice in Share._meta.get_field("privacy").choices
        ]
        if privacy not in valid_privacy:
            raise ValidationError(f"Privacy must be one of {valid_privacy}")

        try:
            with transaction.atomic():
                share = Share.objects.create(
                    user=user,
                    content_object=content_object,
                    caption=caption,
                    privacy=privacy,
                    group=group,
                )
                return share
        except IntegrityError as e:
            raise ValidationError(f"Failed to create share: {str(e)}")

    @staticmethod
    def get_share_by_id(share_id: int) -> Optional[Share]:
        """Retrieve a share by ID (excluding deleted)."""
        try:
            return Share.objects.get(id=share_id, is_deleted=False)
        except Share.DoesNotExist:
            return None

    @staticmethod
    def get_user_shares(
        user: User,
        requester: Optional[User] = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Share]:
        """Get shares created by a specific user, filtered by privacy."""
        queryset = Share.objects.filter(user=user)
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)

        # Apply privacy filtering if requester is not the owner
        if requester and requester != user:
            # Public shares only (we could also allow followers if share privacy = 'followers')
            queryset = queryset.filter(privacy="public")
        elif not requester:
            # Anonymous: only public shares
            queryset = queryset.filter(privacy="public")

        return list(queryset.order_by("-created_at")[offset : offset + limit])

    @staticmethod
    def get_shares_for_object(
        content_object, include_deleted: bool = False, limit: int = 100, offset: int = 0
    ) -> List[Share]:
        """Get all shares of a particular object."""
        content_type = ContentType.objects.get_for_model(content_object)
        queryset = Share.objects.filter(
            content_type=content_type, object_id=content_object.pk
        )
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        return list(queryset.order_by("-created_at")[offset : offset + limit])

    @staticmethod
    def delete_share(share: Share, soft: bool = True) -> bool:
        """Delete a share (soft by default)."""
        try:
            if soft:
                share.is_deleted = True
                share.save(update_fields=["is_deleted"])
            else:
                share.delete()
            return True
        except Exception:
            return False

    @staticmethod
    def restore_share(share: Share) -> bool:
        """Restore a soft‑deleted share."""
        if not share.is_deleted:
            return False
        share.is_deleted = False
        share.save(update_fields=["is_deleted"])
        return True

    @staticmethod
    def update_share(share: Share, caption: str = None, privacy: str = None) -> Share:
        """Update share fields."""
        if share.is_deleted:
            raise ValidationError("Cannot update a deleted share.")

        if caption is not None:
            share.caption = caption
        if privacy is not None:
            valid_privacy = [
                choice[0] for choice in Share._meta.get_field("privacy").choices
            ]
            if privacy not in valid_privacy:
                raise ValidationError(f"Privacy must be one of {valid_privacy}")
            share.privacy = privacy

        share.save()
        return share

    @staticmethod
    def get_share_count(content_object) -> int:
        """Get number of shares for an object (excluding deleted)."""
        content_type = ContentType.objects.get_for_model(content_object)
        return Share.objects.filter(
            content_type=content_type, object_id=content_object.pk, is_deleted=False
        ).count()

    @staticmethod
    def get_recent_shares(
        content_type_model: str = None, limit: int = 20
    ) -> List[Share]:
        """
        Get recent shares across all content, optionally filtered by model name.
        Example: content_type_model = 'post' or 'reel'
        """
        queryset = Share.objects.filter(is_deleted=False)
        if content_type_model:
            app_label, model = (
                content_type_model.split(".")
                if "." in content_type_model
                else ("feed", content_type_model)
            )
            content_type = ContentType.objects.get(app_label=app_label, model=model)
            queryset = queryset.filter(content_type=content_type)
        return list(
            queryset.select_related("user", "content_type").order_by("-created_at")[
                :limit
            ]
        )

    @staticmethod
    def get_user_share_statistics(user: User) -> Dict[str, Any]:
        """Get share statistics for a user."""
        total_shares = Share.objects.filter(user=user, is_deleted=False).count()
        # Breakdown by content type
        from django.db.models import Count

        type_breakdown = (
            Share.objects.filter(user=user, is_deleted=False)
            .values("content_type__model")
            .annotate(count=Count("id"))
        )

        return {
            "total_shares": total_shares,
            "type_breakdown": list(type_breakdown),
            "first_share_date": (
                Share.objects.filter(user=user)
                .order_by("created_at")
                .first()
                .created_at
                if total_shares > 0
                else None
            ),
        }

    @staticmethod
    def get_feed_shares(user: User, limit: int = 50, offset: int = 0) -> List[Share]:
        """
        Return shares that should appear in the user's feed:
        - shares from users the current user follows
        - public shares from others (if we want discovery, not for now)
        For simplicity, only from followed users and own shares.
        """
        following = UserFollowService.get_following(user)
        # Get shares from followed users and own shares
        queryset = (
            Share.objects.filter(Q(user__in=following) | Q(user=user), is_deleted=False)
            .select_related("user", "content_type")
            .order_by("-created_at")
        )

        shares = list(queryset[offset : offset + limit])

        # Prefetch the content objects (assume they are Posts) with their media variants
        if shares:
            # Get the content type for Post model
            post_ct = ContentType.objects.get_for_model(Post)
            # Collect IDs of shares that point to Post objects
            post_ids = [s.object_id for s in shares if s.content_type == post_ct]
            if post_ids:
                # Fetch those Posts with prefetched media and variants
                posts = Post.objects.filter(id__in=post_ids).prefetch_related(
                    Prefetch(
                        "media", queryset=Media.objects.prefetch_related("variants")
                    )
                )
                # Create a mapping from id to post
                post_map = {p.id: p for p in posts}
                # Attach the post to each share as _cached_content_object
                for share in shares:
                    if share.content_type == post_ct and share.object_id in post_map:
                        share._cached_content_object = post_map[share.object_id]

        return shares

    @staticmethod
    def get_group_shares(group, requester=None, limit=20, offset=0):
        """
        Return shares that are posted to a specific group.
        """
        from django.contrib.contenttypes.models import ContentType
        from groups.services.group import GroupService

        # Check if the requester can view the group (optional)
        if requester and not GroupService.is_user_allowed_to_view(requester, group):
            return []

        queryset = (
            Share.objects.filter(
                group=group,
                is_deleted=False,
                # Possibly filter by privacy if share has that field
            )
            .select_related("user", "content_type")
            .order_by("-created_at")
        )

        return list(queryset[offset : offset + limit])
