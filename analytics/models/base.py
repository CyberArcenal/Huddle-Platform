from django.db import models
from users.models import User

class UserAnalytics(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='analytics')
    date = models.DateField()
    posts_count = models.IntegerField(default=0)
    likes_received = models.IntegerField(default=0)
    comments_received = models.IntegerField(default=0)
    new_followers = models.IntegerField(default=0)
    stories_posted = models.IntegerField(default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_analytics'
        unique_together = ('user', 'date')

class PlatformAnalytics(models.Model):
    date = models.DateField(unique=True)
    total_users = models.IntegerField(default=0)
    active_users = models.IntegerField(default=0)
    new_posts = models.IntegerField(default=0)
    new_groups = models.IntegerField(default=0)
    total_messages = models.IntegerField(default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'platform_analytics'