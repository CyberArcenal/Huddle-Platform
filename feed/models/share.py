from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from feed.models.post import POST_PRIVACY_TYPES
from groups.models.group import Group

class Share(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shares'
    )
    group = models.ForeignKey(
        Group,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='shares'
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    caption = models.TextField(blank=True)
    privacy = models.CharField(max_length=10, choices=POST_PRIVACY_TYPES, default='public')
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shares'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['group', 'created_at']),
        ]

    def __str__(self):
        return f"Share {self.id} by {self.user} of {self.content_type} #{self.object_id}"