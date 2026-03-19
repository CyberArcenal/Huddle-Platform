# feed/models/reel.py
from django.db import models
from feed.models.post import POST_PRIVACY_TYPES
from users.models import User

class Reel(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reels')
    caption = models.TextField(blank=True)
    video = models.FileField(upload_to='reels/videos/')          # main video
    thumbnail = models.ImageField(upload_to='reels/thumbnails/', blank=True, null=True)
    audio = models.FileField(upload_to='reels/audio/', blank=True, null=True)  # optional custom audio
    duration = models.FloatField(help_text='Duration in seconds', blank=True, null=True)
    privacy = models.CharField(max_length=10, choices=POST_PRIVACY_TYPES, default='public')
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reels'
        ordering = ['-created_at']

    def __str__(self):
        return f'Reel {self.id} by {self.user.username}'