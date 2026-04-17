from django.db import models
from users.models import User


class DatingMessage(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dating_sent_messages")
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dating_received_messages")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        db_table = "dating_messages"