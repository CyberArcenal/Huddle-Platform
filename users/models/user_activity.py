from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from users.models.base import ACTION_TYPES

class UserActivity(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activities"
    )
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    description = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    location = models.CharField(max_length=250, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        # checker: dapat valid ang action
        valid_actions = [choice[0] for choice in ACTION_TYPES]
        if self.action not in valid_actions:
            raise ValidationError(
                f"Invalid action '{self.action}'. Must be one of {valid_actions}"
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.action} at {self.timestamp}"