from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = get_user_model()

class ObjectBookmark(models.Model):
    """
    Generic model to track saved/bookmarked content (Posts, Reels, Stories, etc.)
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookmarks")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "content_type", "object_id")
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user} bookmarked {self.content_object}"
