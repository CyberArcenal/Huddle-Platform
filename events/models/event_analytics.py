from django.db import models
from events.models import Event


class EventAnalytics(models.Model):
    """Daily analytics for a specific event."""
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='analytics'
    )
    date = models.DateField()
    rsvp_going_count = models.IntegerField(default=0)
    rsvp_maybe_count = models.IntegerField(default=0)
    rsvp_declined_count = models.IntegerField(default=0)
    rsvp_changes = models.IntegerField(default=0)  # total RSVP changes on that day
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'event_analytics'
        unique_together = ('event', 'date')
        ordering = ['-date']