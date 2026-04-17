from django.db import transaction
from django.core.exceptions import ValidationError
from typing import Optional
from dating.models.dating_preference import DatingPreference
from users.models import User

class DatingPreferenceService:
    """Service layer for DatingPreference model operations."""

    @staticmethod
    def create_default_preferences(user: User) -> DatingPreference:
        """Create default dating preferences for a new user."""
        with transaction.atomic():
            preferences, created = DatingPreference.objects.get_or_create(
                user=user,
                defaults={
                    "preferred_age_min": None,
                    "preferred_age_max": None,
                    "preferred_gender": None,
                    "max_distance_km": None,
                    "personality_match": False,
                    "love_language_match": False,
                    "relationship_goal_match": False,
                },
            )
            return preferences

    @staticmethod
    def update_preferences(user: User, update_data: dict) -> DatingPreference:
        """Update dating preferences for a user."""
        try:
            preferences = user.dating_preferences
        except DatingPreference.DoesNotExist:
            preferences = DatingPreferenceService.create_default_preferences(user)

        for field, value in update_data.items():
            if hasattr(preferences, field):
                setattr(preferences, field, value)

        preferences.full_clean()
        preferences.save()
        return preferences

    @staticmethod
    def get_preferences(user: User) -> Optional[DatingPreference]:
        """Retrieve dating preferences for a user."""
        try:
            return user.dating_preferences
        except DatingPreference.DoesNotExist:
            return None

    @staticmethod
    def check_compatibility(user1: User, user2: User) -> bool:
        """Check if two users are compatible based on preferences."""
        prefs1 = DatingPreferenceService.get_preferences(user1)
        prefs2 = DatingPreferenceService.get_preferences(user2)

        if not prefs1 or not prefs2:
            return False

        # Example compatibility rules:
        if prefs1.preferred_gender and prefs1.preferred_gender != user2.gender:
            return False
        if prefs2.preferred_gender and prefs2.preferred_gender != user1.gender:
            return False

        # Age range check (assuming User has age field)
        if prefs1.preferred_age_min and user2.age < prefs1.preferred_age_min:
            return False
        if prefs1.preferred_age_max and user2.age > prefs1.preferred_age_max:
            return False

        if prefs2.preferred_age_min and user1.age < prefs2.preferred_age_min:
            return False
        if prefs2.preferred_age_max and user1.age > prefs2.preferred_age_max:
            return False

        # Distance check (assuming User has location field and you can compute distance)
        # Example placeholder: skip for now

        return True