# admin_pannel/admin.py

from django.contrib import admin
from .models import AdminLog, ReportedContent


@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'admin_user', 'action', 'target_user', 'target_id', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('admin_user__username', 'target_user__username', 'reason')
    readonly_fields = ('created_at',)
    raw_id_fields = ('admin_user', 'target_user')
    date_hierarchy = 'created_at'


@admin.register(ReportedContent)
class ReportedContentAdmin(admin.ModelAdmin):
    list_display = ('id', 'reporter', 'content_type', 'object_id', 'status', 'created_at', 'resolved_at')
    list_filter = ('content_type', 'status', 'created_at')
    search_fields = ('reporter__username', 'reason')
    readonly_fields = ('created_at',)
    raw_id_fields = ('reporter',)
    date_hierarchy = 'created_at'
    actions = ['mark_as_reviewed', 'mark_as_resolved', 'mark_as_dismissed']

    def mark_as_reviewed(self, request, queryset):
        queryset.update(status='reviewed')
    mark_as_reviewed.short_description = "Mark selected reports as reviewed"

    def mark_as_resolved(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='resolved', resolved_at=timezone.now())
    mark_as_resolved.short_description = "Mark selected reports as resolved"

    def mark_as_dismissed(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='dismissed', resolved_at=timezone.now())
    mark_as_dismissed.short_description = "Mark selected reports as dismissed"