from django.conf import settings
from django.db import models

class UserAnalytics(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='analytics')
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