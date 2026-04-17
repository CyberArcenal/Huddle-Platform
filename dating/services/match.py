from django.db import transaction
from django.core.exceptions import ValidationError
from typing import Optional, List, Tuple
from django.db import models
from users.models import User
from dating.models import Match


class MatchService:
    """Service layer for Match model operations."""

    @staticmethod
    def create_match(user1: User, user2: User) -> Match:
        """Create a new match between two users.
        If a match already exists but is inactive, it will be reactivated.
        """
        if user1.id == user2.id:
            raise ValidationError("Cannot match with yourself.")

        # Check existing match in either direction
        existing = Match.objects.filter(
            models.Q(user1=user1, user2=user2) | models.Q(user1=user2, user2=user1)
        ).first()

        if existing:
            if existing.is_active:
                raise ValidationError("Match already exists.")
            else:
                # Reactivate existing match
                existing.is_active = True
                existing.save()
                return existing

        with transaction.atomic():
            return Match.objects.create(user1=user1, user2=user2, is_active=True)

    @staticmethod
    def reactivate_match(match: Match) -> Match:
        """Reactivate an inactive match."""
        if match.is_active:
            raise ValidationError("Match is already active.")
        match.is_active = True
        match.save()
        return match

    @staticmethod
    def deactivate_match(match: Match) -> Match:
        """Deactivate a match (unmatch)."""
        if not match.is_active:
            raise ValidationError("Match is already inactive.")
        match.is_active = False
        match.save()
        return match

    @staticmethod
    def get_match(user1: User, user2: User, include_inactive: bool = False) -> Optional[Match]:
        """Retrieve match record between two users.
        If include_inactive is True, returns any match (active or inactive);
        otherwise returns only active matches.
        """
        qs = Match.objects.filter(
            models.Q(user1=user1, user2=user2) | models.Q(user1=user2, user2=user1)
        )
        if not include_inactive:
            qs = qs.filter(is_active=True)
        return qs.first()

    @staticmethod
    def get_match_by_id(match_id: int, user: User) -> Optional[Match]:
        """Retrieve a match by ID, ensuring the user is part of it."""
        try:
            match = Match.objects.get(pk=match_id)
        except Match.DoesNotExist:
            return None
        if user not in (match.user1, match.user2):
            return None
        return match

    @staticmethod
    def list_matches(user: User, active_only: bool = True) -> List[Match]:
        """List all matches for a user, optionally filtering by active status."""
        qs = Match.objects.filter(
            models.Q(user1=user) | models.Q(user2=user)
        ).select_related('user1', 'user2')
        if active_only:
            qs = qs.filter(is_active=True)
        return qs.order_by('-created_at')

    @staticmethod
    def get_matches_with_pagination(user: User, limit: int = 20, offset: int = 0, active_only: bool = True) -> Tuple[int, List[Match]]:
        """Return a paginated list of matches for a user.
        Returns (total_count, paginated_matches).
        """
        qs = Match.objects.filter(
            models.Q(user1=user) | models.Q(user2=user)
        )
        if active_only:
            qs = qs.filter(is_active=True)
        total = qs.count()
        matches = qs.select_related('user1', 'user2').order_by('-created_at')[offset:offset+limit]
        return total, matches

    @staticmethod
    def get_matched_users(user: User) -> List[User]:
        """Return the other users in all active matches for the given user."""
        matches = Match.objects.filter(is_active=True).filter(
            models.Q(user1=user) | models.Q(user2=user)
        ).select_related('user1', 'user2')
        other_users = []
        for match in matches:
            if match.user1 == user:
                other_users.append(match.user2)
            else:
                other_users.append(match.user1)
        return other_users

    @staticmethod
    def get_match_count(user: User, active_only: bool = True) -> int:
        """Return the number of matches for a user."""
        qs = Match.objects.filter(
            models.Q(user1=user) | models.Q(user2=user)
        )
        if active_only:
            qs = qs.filter(is_active=True)
        return qs.count()

    @staticmethod
    def is_matched(user1: User, user2: User) -> bool:
        """Check if two users are currently matched (active)."""
        return MatchService.get_match(user1, user2) is not None

    @staticmethod
    def get_match_history(user: User) -> List[Match]:
        """Retrieve all matches (active and inactive) for a user, ordered by creation."""
        return Match.objects.filter(
            models.Q(user1=user) | models.Q(user2=user)
        ).select_related('user1', 'user2').order_by('-created_at')