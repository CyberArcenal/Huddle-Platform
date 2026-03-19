from django.db import models
from users.models import User


class ReportedContent(models.Model):
    CONTENT_TYPES = [
        ("post", "Post"),
        ("comment", "Comment"),
        ("user", "User"),
        ("group", "Group"),
    ]

    reporter = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reports_made"
    )
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPES)
    object_id = models.PositiveIntegerField()
    reason = models.TextField()
    status = models.CharField(
        max_length=20, default="pending"
    )  # pending, reviewed, resolved, dismissed
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reported_content"
