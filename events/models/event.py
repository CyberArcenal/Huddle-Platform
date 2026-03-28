from django.conf import settings
from django.db import models
from feed.models.media import Media
from groups.models import Group
from django.contrib.contenttypes.fields import GenericRelation

class Event(models.Model):
    EVENT_TYPES = [
        ("public", "Public Event"),
        ("private", "Private Event"),
        ("group", "Group Event"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organized_events"
    )
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, null=True, blank=True, related_name="events"
    )
    media = GenericRelation(Media, related_query_name='event')
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
