from django.db import models
from users.models import User

GROUP_PRIVACY_CHOICES = [
    ("public", "Public"),
    ("private", "Private"),
    ("secret", "Secret"),
]


class Group(models.Model):

    name = models.CharField(max_length=100)
    description = models.TextField()
    creator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_groups"
    )
    profile_picture = models.ImageField(upload_to="groups/", blank=True, null=True)
    cover_photo = models.ImageField(upload_to="group_covers/", blank=True, null=True)
    privacy = models.CharField(max_length=10, choices=GROUP_PRIVACY_CHOICES, default="public")
    member_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "groups"
