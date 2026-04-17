from django.db import models
from .user import User


class MutedUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="muter")
    muted = models.ForeignKey(User, on_delete=models.CASCADE, related_name="muted_user")
    created_at = models.DateTimeField(auto_now_add=True)