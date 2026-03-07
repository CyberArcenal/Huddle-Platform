# events/admin.py

from django.contrib import admin
from .models import Event, EventAttendance, EventAnalytics


class EventAttendanceInline(admin.TabularInline):
    """Inline for viewing attendances directly under an event."""
    model = EventAttendance
    extra = 0
    raw_id_fields = ('user',)
    readonly_fields = ('joined_at',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'organizer', 'event_type', 'start_time', 'end_time',
                    'attending_count', 'maybe_count', 'declined_count', 'created_at')
    list_filter = ('event_type', 'start_time', 'created_at')
    search_fields = ('title', 'description', 'location', 'organizer__username')
    raw_id_fields = ('organizer', 'group')
    date_hierarchy = 'start_time'
    readonly_fields = ('attending_count', 'maybe_count', 'declined_count', 'created_at')
    inlines = [EventAttendanceInline]


@admin.register(EventAttendance)
class EventAttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'user', 'status', 'joined_at')
    list_filter = ('status', 'joined_at')
    search_fields = ('event__title', 'user__username')
    raw_id_fields = ('event', 'user')
    date_hierarchy = 'joined_at'


@admin.register(EventAnalytics)
class EventAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('event', 'date', 'rsvp_going_count', 'rsvp_maybe_count',
                    'rsvp_declined_count', 'rsvp_changes')
    list_filter = ('date',)
    search_fields = ('event__title',)
    raw_id_fields = ('event',)
    date_hierarchy = 'date'
    readonly_fields = ('created_at', 'updated_at')