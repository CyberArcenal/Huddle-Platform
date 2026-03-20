from django.conf import settings
from django.db import models

class Story(models.Model):
    STORY_TYPES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('text', 'Text'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stories')
    story_type = models.CharField(max_length=10, choices=STORY_TYPES)
    content = models.TextField(blank=True, null=True)
    media_url = models.FileField(upload_to='stories/', blank=True, null=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stories'
        ordering = ['-created_at']