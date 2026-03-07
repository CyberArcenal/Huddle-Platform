from django.db import models
from users.models import User
from groups.models import Group


class Event(models.Model):
    EVENT_TYPES = [
        ("public", "Public Event"),
        ("private", "Private Event"),
        ("group", "Group Event"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    organizer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="organized_events"
    )
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, null=True, blank=True, related_name="events"
    )
    event_type = models.CharField(max_length=10, choices=EVENT_TYPES, default="public")
    location = models.CharField(max_length=255)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    max_attendees = models.IntegerField(null=True, blank=True)
    attending_count = models.IntegerField(default=0)
    maybe_count = models.IntegerField(default=0)
    declined_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "events"


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
        User, on_delete=models.CASCADE, related_name="event_attendances"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="going")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_attendance"
        unique_together = ("event", "user")
