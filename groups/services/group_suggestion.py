from users.models import User
from groups.models import Group
from django.db import models

class GroupSuggestionService:
    @staticmethod
    def suggest_groups(user: User, limit: int = 5):
        qs = Group.objects.all()

        # Match by hobbies, interests, causes, schools, works, personality
        suggestions = qs.filter(
            models.Q(name__in=user.hobbies.values_list("name", flat=True)) |
            models.Q(name__in=user.interests.values_list("name", flat=True)) |
            models.Q(name__in=user.causes.values_list("name", flat=True)) |
            models.Q(name__in=user.schools.values_list("name", flat=True)) |
            models.Q(name__icontains=user.personality_type)
        ).distinct()

        return suggestions[:limit]