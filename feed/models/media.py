from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Media(models.Model):
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
    
    
    
    
    
# FOR FUTURE
# MEDIA_VARIANT_TYPES = [('thumbnail', 'Thumbnail'), ('small', 'Small')]
# class MediaVariant(models.Model):
#     media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='variants')
#     variant_type = models.CharField(max_length=20, choices=MEDIA_VARIANT_TYPES)
#     file = models.FileField(upload_to='media/variants/')
#     width = models.PositiveIntegerField(null=True, blank=True)
#     height = models.PositiveIntegerField(null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)