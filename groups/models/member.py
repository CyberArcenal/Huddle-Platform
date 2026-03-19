from enum import Enum

from django.db import models
from groups.models.group import Group
from users.models import User


class MemberRole(str, Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"


GROUP_ROLE_CHOICES = [
    ("admin", "Admin"),
    ("moderator", "Moderator"),
    ("member", "Member"),
]


class GroupMember(models.Model):

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="group_memberships"
    )
    role = models.CharField(max_length=10, choices=GROUP_ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "group_members"
        unique_together = ("group", "user")
