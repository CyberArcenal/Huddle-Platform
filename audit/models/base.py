from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import json
from datetime import datetime

User = get_user_model()

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('SOFT_DELETE', 'Soft Delete'),
        ('RESTORE', 'Restore'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('CUSTOM', 'Custom'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs',
        help_text="User who performed the action (if authenticated)."
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, db_index=True,
                                  help_text="Name of the affected model.")
    record_id = models.CharField(max_length=100, blank=True, null=True,
                                 help_text="Primary key of the affected record.")
    old_data = models.JSONField(default=dict, blank=True,
                                help_text="Previous state (for UPDATE/DELETE).")
    new_data = models.JSONField(default=dict, blank=True,
                                help_text="New state (for CREATE/UPDATE).")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    message = models.TextField(blank=True,
                               help_text="Optional additional description.")

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['model_name', 'record_id']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} on {self.model_name} (ID:{self.record_id}) by {self.user or 'Anonymous'} at {self.created_at}"