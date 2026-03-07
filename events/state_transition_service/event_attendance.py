from django.db.models import F
from events.models import Event
from events.services.event_analytics import EventAnalyticsService
from notifications.services.notification import NotificationService


class EventAttendanceStateTransitionService:
    """Handles side effects of attendance status changes."""

    @staticmethod
    def handle_status_change(attendance, old_status, new_status):
        """Called when attendance status changes (or when created)."""
        event = attendance.event
        user = attendance.user

        # 1. Update event's attendance counts
        EventAttendanceStateTransitionService._update_event_counts(event, old_status, new_status)

        # 2. Notify the event organizer (unless the change is made by the organizer themselves)
        if event.organizer != user:
            NotificationService.send_rsvp_change_notification(
                organizer=event.organizer,
                event=event,
                attendee=user,
                old_status=old_status,
                new_status=new_status
            )

        # 3. Update analytics (record the change)
        EventAnalyticsService.record_rsvp_change(
            event=event,
            old_status=old_status,
            new_status=new_status
        )

    @staticmethod
    def _update_event_counts(event, old_status, new_status):
        """Update the aggregate counts on the Event model."""
        count_fields = {
            'going': 'attending_count',
            'maybe': 'maybe_count',
            'declined': 'declined_count'
        }

        # Decrement old status
        if old_status and old_status in count_fields:
            field = count_fields[old_status]
            setattr(event, field, F(field) - 1)

        # Increment new status
        if new_status and new_status in count_fields:
            field = count_fields[new_status]
            setattr(event, field, F(field) + 1)

        # Save only the count fields
        event.save(update_fields=list(count_fields.values()))
        event.refresh_from_db()