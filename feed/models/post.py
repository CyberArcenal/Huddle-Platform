from django.conf import settings
from django.db import models
from feed.models.media import Media
from groups.models.group import Group
from django.contrib.contenttypes.fields import GenericRelation


POST_TYPES = [
    ("text", "Text"),
    ("image", "Image"),
    ("video", "Video"),
    ("poll", "Poll"),
    ("share", "Share"),
]
POST_PRIVACY_TYPES = [
    ("public", "Public"),
    ("followers", "Followers"),
    ("secret", "Secret"),
]


class Post(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts"
    )
    media = GenericRelation(Media, related_query_name='post')
    group = models.ForeignKey(
        Group, null=True, blank=True, on_delete=models.CASCADE, related_name="posts"
    )
    shared_post = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="shares"
    )
    tag_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="tagged_posts", blank=True
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
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["group", "created_at"]),
        ]
