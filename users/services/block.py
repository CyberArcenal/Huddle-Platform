from django.db import transaction
from django.core.exceptions import ValidationError
from typing import Optional, List
from ..models import BlockedUser, User


class BlockedUserService:
    """Service layer for BlockedUser model operations."""

    @staticmethod
    def block_user(user: User, blocked: User) -> BlockedUser:
        """Block another user."""
        if user.id == blocked.id:
            raise ValidationError("Cannot block yourself.")

        existing = BlockedUser.objects.filter(user=user, blocked=blocked).first()
        if existing:
            raise ValidationError("User is already blocked.")

        with transaction.atomic():
            blocked_user = BlockedUser.objects.create(
                user=user,
                blocked=blocked,
            )
            return blocked_user

    @staticmethod
    def unblock_user(user: User, blocked: User) -> bool:
        """Unblock a user."""
        try:
            with transaction.atomic():
                record = BlockedUser.objects.get(user=user, blocked=blocked)
                record.delete()
                return True
        except BlockedUser.DoesNotExist:
            raise ValidationError("Blocked record does not exist.")
        except Exception:
            return False

    @staticmethod
    def list_blocked_users(user: User) -> List[BlockedUser]:
        """List all blocked users for a given user."""
        return BlockedUser.objects.filter(user=user)

    @staticmethod
    def is_blocked(user: User, blocked: User) -> bool:
        """Check if a user is blocked."""
        return BlockedUser.objects.filter(user=user, blocked=blocked).exists()

    @staticmethod
    def get_block_record(user: User, blocked: User) -> Optional[BlockedUser]:
        """Retrieve block record between two users."""
        return BlockedUser.objects.filter(user=user, blocked=blocked).first()
    
    @staticmethod
    def get_blocked_ids(user: User) -> set:
        """Return a set of user IDs that the given user has blocked."""
        return set(BlockedUser.objects.filter(user=user).values_list('blocked_id', flat=True))