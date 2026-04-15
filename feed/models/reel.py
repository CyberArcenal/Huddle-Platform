# feed/models/reel.py
from django.conf import settings
from django.db import models
from feed.models.post import POST_PRIVACY_TYPES
from django.contrib.contenttypes.fields import GenericRelation

from feed.models.media import Media
from groups.models.group import Group




class Reel(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reels')
    group = models.ForeignKey(
        Group, null=True, blank=True, on_delete=models.CASCADE, related_name="reels"
    )
    caption = models.TextField(blank=True)
    media = GenericRelation(Media, related_query_name='reel')        # main video
    thumbnail = models.ImageField(upload_to='reels/thumbnails/', blank=True, null=True)
    thumbnail_variant = models.OneToOneField(
        'MediaVariant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reel_thumbnail'
    )
    audio = models.FileField(upload_to='reels/audio/', blank=True, null=True)  # optional custom audio
    duration = models.FloatField(help_text='Duration in seconds', blank=True, null=True)
    privacy = models.CharField(max_length=10, choices=POST_PRIVACY_TYPES, default='public')
    is_deleted = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    
    client_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    processing = models.BooleanField(default=True)
    temp_file_path = models.CharField(max_length=500, blank=True, null=True)
    

    class Meta:
        db_table = 'reels'
        ordering = ['-created_at']

    def __str__(self):
        return f'Reel {self.id} by {self.user.username}'