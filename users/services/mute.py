from django.db import transaction
from django.core.exceptions import ValidationError
from typing import Optional, List
from ..models import MutedUser, User


class MutedUserService:
    """Service layer for MutedUser model operations."""

    @staticmethod
    def mute_user(user: User, muted: User) -> MutedUser:
        """Mute another user."""
        if user.id == muted.id:
            raise ValidationError("Cannot mute yourself.")

        existing = MutedUser.objects.filter(user=user, muted=muted).first()
        if existing:
            raise ValidationError("User is already muted.")

        with transaction.atomic():
            muted_user = MutedUser.objects.create(
                user=user,
                muted=muted,
            )
            return muted_user

    @staticmethod
    def unmute_user(user: User, muted: User) -> bool:
        """Unmute a user."""
        try:
            with transaction.atomic():
                record = MutedUser.objects.get(user=user, muted=muted)
                record.delete()
                return True
        except MutedUser.DoesNotExist:
            raise ValidationError("Mute record does not exist.")
        except Exception:
            return False

    @staticmethod
    def list_muted_users(user: User) -> List[MutedUser]:
        """List all muted users for a given user."""
        return MutedUser.objects.filter(user=user)

    @staticmethod
    def is_muted(user: User, muted: User) -> bool:
        """Check if a user is muted."""
        return MutedUser.objects.filter(user=user, muted=muted).exists()

    @staticmethod
    def get_mute_record(user: User, muted: User) -> Optional[MutedUser]:
        """Retrieve mute record between two users."""
        return MutedUser.objects.filter(user=user, muted=muted).first()