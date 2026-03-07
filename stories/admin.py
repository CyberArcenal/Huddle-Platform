# stories/admin.py

from django.contrib import admin
from .models import Story, StoryView


class StoryViewInline(admin.TabularInline):
    """Inline for views under a story."""
    model = StoryView
    extra = 0
    raw_id_fields = ('user',)
    readonly_fields = ('viewed_at',)


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'story_type', 'is_active', 'expires_at', 'created_at')
    list_filter = ('story_type', 'is_active', 'created_at')
    search_fields = ('content', 'user__username')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    inlines = [StoryViewInline]


@admin.register(StoryView)
class StoryViewAdmin(admin.ModelAdmin):
    list_display = ('id', 'story', 'user', 'viewed_at')
    list_filter = ('viewed_at',)
    search_fields = ('story__user__username', 'user__username')
    raw_id_fields = ('story', 'user')
    date_hierarchy = 'viewed_at'
    readonly_fields = ('viewed_at',)