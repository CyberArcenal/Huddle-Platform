from django.conf import settings
from django.utils import timezone
from django.db import models


class UserSecuritySettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="security_settings",
    )
    two_factor_enabled = models.BooleanField(default=False)
    recovery_email = models.EmailField(blank=True, null=True)
    recovery_phone = models.CharField(max_length=20, blank=True, null=True)
    alert_on_new_device = models.BooleanField(default=True)
    alert_on_password_change = models.BooleanField(default=True)
    alert_on_failed_login = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    is_deleted = models.BooleanField(default=False)

    def delete(self, using=None, keep_parents=False):
        """Soft delete instead of hard delete"""
        self.is_deleted = True
        self.save()

    def __str__(self):
        return f"Security settings for {self.user.username}"