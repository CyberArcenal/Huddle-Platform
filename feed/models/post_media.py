from django.db import models
from feed.models.post import Post


class PostMedia(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="media")
    file = models.FileField(
        upload_to="posts/", blank=True, null=True
    )  # Accepts any file (images, videos)
    order = models.PositiveIntegerField(default=0, help_text="Order of display")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "post_media"
        ordering = ["order", "created_at"]
