# messaging/admin.py

from django.contrib import admin
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    """Inline for messages under a conversation."""
    model = Message
    extra = 0
    raw_id_fields = ('sender',)
    readonly_fields = ('created_at',)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'conversation_type', 'participant_count', 'created_at', 'updated_at')
    list_filter = ('conversation_type', 'created_at')
    search_fields = ('name',)
    filter_horizontal = ('participants',)  # or raw_id_fields if many participants
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')
    inlines = [MessageInline]

    def participant_count(self, obj):
        return obj.participants.count()
    participant_count.short_description = 'Participants'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'content_preview', 'is_read', 'is_deleted', 'created_at')
    list_filter = ('is_read', 'is_deleted', 'created_at')
    search_fields = ('content', 'sender__username')
    raw_id_fields = ('conversation', 'sender')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    def content_preview(self, obj):
        return obj.content[:50] + ('...' if len(obj.content) > 50 else '')
    content_preview.short_description = 'Content'