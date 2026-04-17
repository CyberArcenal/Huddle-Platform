from django.db import models
from .user import User

class BlockedUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocker")
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocked_user")
    created_at = models.DateTimeField(auto_now_add=True)