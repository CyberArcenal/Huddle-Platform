from django.db import models
from users.models import User

class DatingPreference(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="dating_preferences"
    )
    preferred_age_min = models.IntegerField(null=True, blank=True)
    preferred_age_max = models.IntegerField(null=True, blank=True)
    preferred_gender = models.CharField(max_length=20, null=True, blank=True)
    max_distance_km = models.IntegerField(null=True, blank=True)

    personality_match = models.BooleanField(default=False)
    love_language_match = models.BooleanField(default=False)
    relationship_goal_match = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dating_preferences"