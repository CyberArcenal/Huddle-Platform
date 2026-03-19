from django.db import models
from users.models import User

class AdminLog(models.Model):
    ACTION_CHOICES = [
        ('user_ban', 'User Ban'),
        ('user_warn', 'User Warning'),
        ('post_remove', 'Post Removal'),
        ('group_remove', 'Group Removal'),
        ('content_review', 'Content Review'),
    ]
    
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_actions')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='admin_logs')
    target_id = models.PositiveIntegerField(null=True, blank=True)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_logs'