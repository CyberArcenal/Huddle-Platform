# feed/services/reel.py
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from typing import Optional, List, Dict, Any
from django.db.models import Prefetch
from django.db import models
from feed.models.media import Media
from feed.services.comment import CommentService
from feed.services.reaction import ReactionService
from users.models import User
from django.contrib.contenttypes.models import ContentType
from ..models import Reel


class ReelService:
    """Service for Reel model operations"""

    @staticmethod
    def create_reel(
        user: User,
        video,
        caption: str = "",
        thumbnail=None,
        audio=None,
        duration: Optional[float] = None,
        privacy: str = "public",
        **extra_fields,
    ) -> Reel:
        """Create a new reel with video file and optional thumbnail."""
        if not video:
            raise ValidationError("Video file is required for a reel.")

        try:
            with transaction.atomic():
                reel = Reel.objects.create(
                    user=user,
                    caption=caption,
                    thumbnail=thumbnail,  # This will be saved
                    audio=audio,
                    duration=duration,
                    privacy=privacy,
                    **extra_fields,
                )
                # Create media for the video
                video_ct = ContentType.objects.get_for_model(reel)
                video_media = Media.objects.create(
                    content_type=video_ct,
                    object_id=reel.id,
                    file=video,
                    order=0,
                    created_by=user,
                )
                # If a thumbnail was saved, we can add its path to the video media metadata
                if reel.thumbnail:
                    video_media.metadata["thumbnail_path"] = reel.thumbnail.name
                    video_media.save(update_fields=["metadata"])
                return reel
        except IntegrityError as e:
            raise ValidationError(f"Failed to create reel: {str(e)}")

    @staticmethod
    def get_reel_by_id(reel_id: int) -> Optional[Reel]:
        """Retrieve reel by ID (excluding deleted)."""
        try:
            return Reel.objects.get(id=reel_id, is_deleted=False)
        except Reel.DoesNotExist:
            return None

    @staticmethod
    def get_user_reels(
        user: User,
        requester: Optional[User] = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Reel]:
        """Get reels by a specific user with privacy filtering."""
        queryset = Reel.objects.filter(user=user)
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)

        if requester and requester != user:
            # Public reels only (or followers if we implement that)
            queryset = queryset.filter(privacy="public")
        elif not requester:
            queryset = queryset.filter(privacy="public")
        return list(queryset.order_by("-created_at")[offset : offset + limit])

    @staticmethod
    def get_public_reels(
        exclude_user: Optional[User] = None, limit: int = 50, offset: int = 0
    ) -> List[Reel]:
        """Get public reels from all users."""
        queryset = Reel.objects.filter(privacy="public", is_deleted=False)
        if exclude_user:
            queryset = queryset.exclude(user=exclude_user)
        return list(queryset.order_by("-created_at")[offset : offset + limit])

    @staticmethod
    def get_feed_reels(user: User, limit: int = 50, offset: int = 0) -> List[Reel]:
        """Get personalized reel feed for a user (from followed users and self)."""
        from users.services import UserFollowService

        following_users = UserFollowService.get_following(user)
        feed_reels = (
            Reel.objects.filter(
                models.Q(user__in=following_users) | models.Q(user=user),
                is_deleted=False,
                privacy__in=[
                    "public",
                    "followers",
                ],  # followers can see followers-only reels from followed users
            )
            .select_related("user")
            .prefetch_related(
                Prefetch('media', queryset=Media.objects.prefetch_related('variants'))
            )
            .order_by("-created_at")[offset : offset + limit]
        )
        return list(feed_reels)

    @staticmethod
    def update_reel(reel: Reel, update_data: Dict[str, Any]) -> Reel:
        """Update reel fields (except video)."""
        if reel.is_deleted:
            raise ValidationError("Cannot update a deleted reel.")

        allowed_fields = {"caption", "thumbnail", "audio", "duration", "privacy"}
        try:
            with transaction.atomic():
                for field, value in update_data.items():
                    if field in allowed_fields and hasattr(reel, field):
                        setattr(reel, field, value)
                reel.full_clean()
                reel.save()
                return reel
        except ValidationError as e:
            raise

    @staticmethod
    def delete_reel(reel: Reel, soft_delete: bool = True) -> bool:
        """Delete a reel (soft or hard)."""
        try:
            if soft_delete:
                reel.is_deleted = True
                reel.save()
            else:
                reel.delete()
            return True
        except Exception:
            return False

    @staticmethod
    def restore_reel(reel: Reel) -> bool:
        """Restore a soft‑deleted reel."""
        if not reel.is_deleted:
            return False
        reel.is_deleted = False
        reel.save()
        return True

    @staticmethod
    def search_reels(
        query: str, user: Optional[User] = None, limit: int = 20, offset: int = 0
    ) -> List[Reel]:
        """Search reels by caption."""
        queryset = Reel.objects.filter(caption__icontains=query, is_deleted=False)
        if user:
            queryset = queryset.filter(user=user)
        return list(queryset.order_by("-created_at")[offset : offset + limit])

    @staticmethod
    def get_reel_statistics(reel: Reel) -> Dict[str, Any]:
        """Get like and comment counts for a reel."""

        return {
            "reel_id": reel.id,
            "like_count": ReactionService.get_like_count("reel", reel.id),
            "comment_count": CommentService.get_comment_count(reel),
            "created_at": reel.created_at,
            "privacy": reel.privacy,
        }

    @staticmethod
    def get_user_reel_statistics(user: User) -> Dict[str, Any]:
        """Get statistics for a user's reels."""
        total_reels = Reel.objects.filter(user=user, is_deleted=False).count()
        public_reels = Reel.objects.filter(
            user=user, privacy="public", is_deleted=False
        ).count()

        # Privacy breakdown
        privacy_breakdown = (
            Reel.objects.filter(user=user, is_deleted=False)
            .values("privacy")
            .annotate(count=models.Count("id"))
        )

        total_likes = 0
        for reel in Reel.objects.filter(user=user, is_deleted=False):
            total_likes += ReactionService.get_like_count("reel", reel.id)

        return {
            "total_reels": total_reels,
            "public_reels": public_reels,
            "private_reels": total_reels - public_reels,
            "privacy_breakdown": list(privacy_breakdown),
            "total_likes": total_likes,
            "first_reel_date": (
                Reel.objects.filter(user=user).order_by("created_at").first().created_at
                if total_reels > 0
                else None
            ),
        }

    @staticmethod
    def get_trending_reels(
        hours: int = 24, min_likes: int = 5, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get trending reels (most liked within a time period)."""

        time_threshold = timezone.now() - timezone.timedelta(hours=hours)

        recent_reels = Reel.objects.filter(
            created_at__gte=time_threshold, is_deleted=False, privacy="public"
        )

        trending = []
        for reel in recent_reels:
            like_count = ReactionService.get_like_count("reel", reel.id)
            if like_count >= min_likes:
                trending.append(
                    {
                        "reel": reel,
                        "like_count": like_count,
                        "comment_count": reel.comments.count(),
                    }
                )

        trending.sort(
            key=lambda x: (-x["like_count"], -x["reel"].created_at.timestamp())
        )
        return trending[:limit]

    @staticmethod
    def cleanup_deleted_reels(days: int = 30) -> int:
        """Permanently delete reels soft‑deleted more than X days ago."""
        threshold = timezone.now() - timezone.timedelta(days=days)
        old_deleted = Reel.objects.filter(is_deleted=True, updated_at__lt=threshold)
        count = old_deleted.count()
        old_deleted.delete()
        return count

    @staticmethod
    def get_group_reels(group, requester=None, limit=20, offset=0):
        """
        Return reels that belong to a specific group.
        Assumes the Reel model has a 'group' field (ForeignKey to Group).
        """
        from groups.services.group import GroupService

        if requester and not GroupService.is_user_allowed_to_view(requester, group):
            return []

        queryset = Reel.objects.filter(
            group=group,
            is_deleted=False,
            # optionally privacy filtering
        ).select_related('user').order_by('-created_at')

        return list(queryset[offset:offset + limit])
