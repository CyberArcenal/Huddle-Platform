from django.db import models
from users.models import User

class PlatformAnalytics(models.Model):
    date = models.DateField(unique=True)
    total_users = models.IntegerField(default=0)
    active_users = models.IntegerField(default=0)
    new_posts = models.IntegerField(default=0)
    new_groups = models.IntegerField(default=0)
    total_messages = models.IntegerField(default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)
    pending_reports = models.IntegerField(default=0)
    reviewed_reports = models.IntegerField(default=0)
    resolved_reports = models.IntegerField(default=0)
    dismissed_reports = models.IntegerField(default=0)
    active_stories = models.IntegerField(default=0)

    class Meta:
        db_table = 'platform_analytics'