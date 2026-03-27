from django.conf import settings
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Media(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='media_uploads'
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    file = models.FileField(upload_to='media/')   # generic path
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'media'   # new table name (optional, but cleaner)
        ordering = ['order']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"Media {self.id} for {self.content_type}"
    
    
    
    
    
MEDIA_VARIANT_TYPES = [
    ('thumbnail', 'Thumbnail'),
    ('small', 'Small'),
    ('medium', 'Medium'),
    ('large', 'Large'),
    ('video_preview', 'Video Preview'),
    ('video_transcoded', 'Video Transcoded'),
]

class MediaVariant(models.Model):
    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='variants')
    variant_type = models.CharField(max_length=30, choices=MEDIA_VARIANT_TYPES)
    file = models.FileField(upload_to='media/variants/')
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration = models.FloatField(null=True, blank=True)   # ✅ for video
    codec = models.CharField(max_length=50, null=True, blank=True)  # ✅ for video
    size_bytes = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'media_variants'
        unique_together = ('media', 'variant_type')

    def __str__(self):
        return f"{self.variant_type} variant for Media {self.media_id}"