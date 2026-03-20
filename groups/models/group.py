from django.conf import settings
from django.db import models


GROUP_PRIVACY_CHOICES = [
    ("public", "Public"),
    ("private", "Private"),
    ("secret", "Secret"),
]

GROUP_TYPE_CHOICES = [
    ("hobby", "Hobby"),
    ("interest", "Interest"),
    ("school", "School"),
    ("work", "Work"),
    ("cause", "Cause"),
    ("personality", "Personality"),
    ("location", "Location"),
    ("achievement", "Achievement"),
]

class Group(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_groups"
    )
    profile_picture = models.ImageField(upload_to="groups/", blank=True, null=True)
    cover_photo = models.ImageField(upload_to="group_covers/", blank=True, null=True)
    privacy = models.CharField(max_length=10, choices=GROUP_PRIVACY_CHOICES, default="public")
    group_type = models.CharField(max_length=20, choices=GROUP_TYPE_CHOICES, default="hobby")
    member_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "groups"
