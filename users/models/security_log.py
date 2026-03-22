from django.conf import settings
from django.utils import timezone
from django.db import models

from users.models.utilities import SECURITY_EVENT_TYPES

class SecurityLog(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="security_logs"
    )

    event_type = models.CharField(max_length=50, choices=SECURITY_EVENT_TYPES)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    details = models.TextField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)

    def delete(self, using=None, keep_parents=False):
        """Soft delete instead of hard delete"""
        self.is_deleted = True
        self.save()

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.event_type} @ {self.created_at}"