from django.db import models
from users.models import User


class Match(models.Model):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="matches_initiated")
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="matches_received")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "matches"
        unique_together = ("user1", "user2")
