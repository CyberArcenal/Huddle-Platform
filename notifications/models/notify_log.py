from django.db import models
from django.utils import timezone

from notifications.models.email_template import TEMPLATE_CHOICES


class NotifyLog(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("resend", "Resend"),
    ]
    
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255, null=True, blank=True)
    payload = models.TextField(null=True, blank=True)
    type = models.CharField(
        max_length=50,
        choices=TEMPLATE_CHOICES,
        default="custom",
        help_text="Template type for this notification"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="queued",
    )
    error_message = models.TextField(null=True, blank=True)
    channel = models.CharField(max_length=50, default="email")
    priority = models.CharField(
        max_length=20, default="normal", help_text="Email priority level"
    )
    message_id = models.CharField(max_length=255, null=True, blank=True)
    duration_ms = models.PositiveIntegerField(
        null=True, blank=True, help_text="Send duration in milliseconds"
    )
    retry_count = models.PositiveIntegerField(default=0)
    resend_count = models.PositiveIntegerField(
        default=0, help_text="Manual resend attempts"
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "notify_logs"
        indexes = [
            models.Index(fields=["status"], name="idx_notify_status"),
            models.Index(fields=["recipient_email"], name="idx_notify_recipient"),
            models.Index(
                fields=["status", "created_at"], name="idx_notify_status_created"
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient_email} - {self.status}"
