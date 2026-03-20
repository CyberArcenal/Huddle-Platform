from django.conf import settings
from django.db import models

class SearchHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='search_history', null=True, blank=True)
    query = models.CharField(max_length=255)
    search_type = models.CharField(max_length=20, default='all')  # 'all', 'users', 'groups', 'posts'
    results_count = models.IntegerField(default=0)
    searched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'search_history'
        ordering = ['-searched_at']