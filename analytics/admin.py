# analytics/admin.py

from django.contrib import admin
from .models import UserAnalytics, PlatformAnalytics


@admin.register(UserAnalytics)
class UserAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'posts_count', 'likes_received', 'comments_received',
                    'new_followers', 'stories_posted')
    list_filter = ('date',)
    search_fields = ('user__username', 'user__email')
    date_hierarchy = 'date'
    readonly_fields = ('recorded_at',)
    raw_id_fields = ('user',)


@admin.register(PlatformAnalytics)
class PlatformAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('date', 'total_users', 'active_users', 'new_posts', 'new_groups',
                    'total_messages', 'pending_reports', 'reviewed_reports',
                    'resolved_reports', 'dismissed_reports', 'active_stories')
    list_filter = ('date',)
    date_hierarchy = 'date'
    readonly_fields = ('recorded_at',)