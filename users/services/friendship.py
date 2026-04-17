from django.db import transaction
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from typing import Optional, List
from ..models import Friendship, User


class FriendshipService:
    """Service layer for Friendship model operations."""

    @staticmethod
    def send_request(from_user: User, to_user: User, tag: str = "normal") -> Friendship:
        """Send a friendship request."""
        if from_user.id == to_user.id:
            raise ValidationError("Cannot send a friend request to yourself.")

        # Check if already exists
        existing = Friendship.objects.filter(user=from_user, friend=to_user).first()
        if existing:
            raise ValidationError("Friendship request already exists.")

        with transaction.atomic():
            friendship = Friendship.objects.create(
                user=from_user,
                friend=to_user,
                status="pending",
                tag=tag,
            )
            return friendship

    @staticmethod
    def accept_request(friendship: Friendship) -> Friendship:
        """Accept a friendship request."""
        if friendship.status != "pending":
            raise ValidationError("Only pending requests can be accepted.")

        friendship.status = "accepted"
        friendship.save()

        # Optionally create mirrored record for easier queries
        Friendship.objects.get_or_create(
            user=friendship.friend,
            friend=friendship.user,
            defaults={"status": "accepted", "tag": "normal"},
        )
        return friendship

    @staticmethod
    def decline_request(friendship: Friendship) -> Friendship:
        """Decline a friendship request."""
        if friendship.status != "pending":
            raise ValidationError("Only pending requests can be declined.")

        friendship.status = "declined"
        friendship.save()
        return friendship

    @staticmethod
    def update_tag(friendship: Friendship, new_tag: str) -> Friendship:
        """Update friendship tag (favorite, pinned, family, etc.)."""
        friendship.tag = new_tag
        friendship.save()
        return friendship

    @staticmethod
    def remove_friendship(friendship: Friendship) -> bool:
        """Remove friendship (unfriend)."""
        try:
            with transaction.atomic():
                friendship.delete()
                return True
        except Exception:
            return False

    @staticmethod
    def list_friends(user: User) -> List[Friendship]:
        """List all accepted friendships for a user."""
        return Friendship.objects.filter(user=user, status="accepted")

    @staticmethod
    def get_friendship(user: User, friend: User) -> Optional[Friendship]:
        """Retrieve friendship record between two users."""
        return Friendship.objects.filter(user=user, friend=friend).first()