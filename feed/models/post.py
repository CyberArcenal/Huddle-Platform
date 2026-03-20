from django.conf import settings
from django.db import models
from groups.models.group import Group

POST_TYPES = [
    ("text", "Text"),
    ("image", "Image"),
    ("video", "Video"),
    ("poll", "Poll"),
    ("share", "Share"),
]
POST_PRIVACY_TYPES = [("public", "Public"), ("followers", "Followers"), ("secret", "Secret")]


class Post(models.Model):

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts")
    group = models.ForeignKey(
        Group,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='posts'
    )
    shared_post = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='shares'
    )
    # ..
    content = models.TextField()
    post_type = models.CharField(max_length=10, choices=POST_TYPES, default="text")
    # media_url removed
    privacy = models.CharField(
        max_length=10, choices=POST_PRIVACY_TYPES, default="followers"
    )
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "posts"
        ordering = ["-created_at"]
