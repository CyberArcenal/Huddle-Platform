from django.contrib import admin

from audit.models.base import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'model_name', 'record_id')
    list_filter = ('action', 'model_name')
    search_fields = ('record_id', 'user__username')
    readonly_fields = ('created_at',)