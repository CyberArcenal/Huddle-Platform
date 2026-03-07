# groups/admin.py

from django.contrib import admin
from .models import Group, GroupMember


class GroupMemberInline(admin.TabularInline):
    """Inline for members under a group."""
    model = GroupMember
    extra = 0
    raw_id_fields = ('user',)
    readonly_fields = ('joined_at',)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'creator', 'privacy', 'member_count', 'created_at')
    list_filter = ('privacy', 'created_at')
    search_fields = ('name', 'description', 'creator__username')
    raw_id_fields = ('creator',)
    date_hierarchy = 'created_at'
    readonly_fields = ('member_count', 'created_at')
    inlines = [GroupMemberInline]


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'group', 'user', 'role', 'joined_at')
    list_filter = ('role', 'joined_at')
    search_fields = ('group__name', 'user__username')
    raw_id_fields = ('group', 'user')
    date_hierarchy = 'joined_at'
    readonly_fields = ('joined_at',)