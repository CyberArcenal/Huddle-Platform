from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from feed.models.post import Post



class Share(Post):
    # Generic relation to the shared object (could be Post, Media, Poll, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    caption = models.TextField(blank=True, help_text="Optional message when sharing")

    class Meta:
        db_table = "shares"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Share {self.id} by {self.user} of {self.content_type} #{self.object_id}"
