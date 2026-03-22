from django.conf import settings
from django.db import models
from groups.models import Group
from .event import Event


class EventAttendance(models.Model):
    STATUS_CHOICES = [
        ("going", "Going"),
        ("maybe", "Maybe"),
        ("declined", "Declined"),
    ]

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="attendances"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_attendances"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="going")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_attendance"
        unique_together = ("event", "user")
