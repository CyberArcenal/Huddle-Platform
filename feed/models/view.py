from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = get_user_model()

class ObjectView(models.Model):
    """
    Generic model to track views on any content object (Post, Story, Reel, etc.)
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="object_views",
        null=True,
        blank=True,
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    viewed_at = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.PositiveIntegerField(default=0)  # how long the view lasted

    class Meta:
        unique_together = ("user", "content_type", "object_id")
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user} viewed {self.content_object} for {self.duration_seconds}s"
