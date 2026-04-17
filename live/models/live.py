from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.utils import timezone

from feed.models.media import Media  # for thumbnail / recorded stream


class LiveStream(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('live', 'Live'),
        ('ended', 'Ended'),
        ('canceled', 'Canceled'),
    )

    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hosted_lives')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    livekit_room = models.CharField(max_length=100, unique=True, null=True, blank=True)  # optional, for integration
    host_token = models.TextField(blank=True)   # o kaya CharField(max_length=1000)  # optional, or generate on the fly

    # Optional: recorded video / thumbnail
    recorded_media = models.ForeignKey(Media, null=True, blank=True, on_delete=models.SET_NULL, related_name='live_recording')
    thumbnail = models.ImageField(upload_to='live/thumbnails/', blank=True, null=True)

    # Settings
    allow_requests = models.BooleanField(default=True)          # can viewers request to join?
    max_participants = models.PositiveIntegerField(default=10)  # max concurrent participants (including host)
    is_private = models.BooleanField(default=False)             # only allowed users can see/request

    # For stream key / ingestion (if using external streaming)
    stream_key = models.CharField(max_length=100, unique=True, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'live_streams'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'started_at']),
            models.Index(fields=['host', 'status']),
        ]

    def __str__(self):
        return f"Live {self.id} by {self.host.username}"


class LiveParticipant(models.Model):
    ROLE_CHOICES = (
        ('host', 'Host'),
        ('co_host', 'Co‑host'),
        ('viewer', 'Viewer'),
    )
    live = models.ForeignKey(LiveStream, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='live_participations')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='viewer')
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'live_participants'
        unique_together = ('live', 'user')
        indexes = [models.Index(fields=['live', 'role'])]

    def __str__(self):
        return f"{self.user.username} in live {self.live.id} as {self.role}"


class LiveJoinRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('canceled', 'Canceled'),
    )
    live = models.ForeignKey(LiveStream, on_delete=models.CASCADE, related_name='join_requests')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='live_join_requests')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    message = models.CharField(max_length=255, blank=True)   # optional message to host

    class Meta:
        db_table = 'live_join_requests'
        unique_together = ('live', 'user')
        ordering = ['requested_at']

    def __str__(self):
        return f"{self.user.username} request for live {self.live.id} ({self.status})"