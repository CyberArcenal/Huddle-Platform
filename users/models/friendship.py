from django.db import models
from .user import User

STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
    ]

RELATIONSHIP_TAGS = [
        ("normal", "Normal"),
        ("favorite", "Favorite"),
        ("pinned", "Pinned"),
        ("close", "Close Contact"),
        ("family", "Family"),
        ("workmate", "Workmate"),
        ("bestfriend", "Best Friend"),
        ("acquaintance", "Acquaintance"),
    ]


class Friendship(models.Model):
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_requests")
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_requests")
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    tag = models.CharField(max_length=20, choices=RELATIONSHIP_TAGS, default="normal")






