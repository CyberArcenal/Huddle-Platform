from django.utils import timezone
from django.db import transaction, IntegrityError
from django.db.models import F
from typing import Optional
import datetime
from events.models import Event
from events.models.event_analytics import EventAnalytics


class EventAnalyticsService:
    """Service for EventAnalytics model operations."""

    @staticmethod
    def get_or_create_daily_analytics(
        event: Event,
        date: Optional[datetime.date] = None
    ) -> EventAnalytics:
        """Get or create analytics record for an event on a given date."""
        if date is None:
            date = timezone.now().date()

        try:
            analytics, created = EventAnalytics.objects.get_or_create(
                event=event,
                date=date,
                defaults={
                    'rsvp_going_count': 0,
                    'rsvp_maybe_count': 0,
                    'rsvp_declined_count': 0,
                    'rsvp_changes': 0,
                }
            )
            return analytics
        except IntegrityError:
            # Race condition – fetch existing
            return EventAnalytics.objects.get(event=event, date=date)

    @staticmethod
    def record_rsvp_change(
        event: Event,
        old_status: Optional[str],
        new_status: str,
        date: Optional[datetime.date] = None
    ) -> EventAnalytics:
        """
        Record an RSVP status change for analytics.
        - old_status: previous status (None for new RSVP)
        - new_status: new status
        """
        analytics = EventAnalyticsService.get_or_create_daily_analytics(event, date)

        # Use F expressions to avoid race conditions
        update_fields = {}

        # Decrement old status count (if any)
        if old_status:
            old_field = f"rsvp_{old_status}_count"
            if hasattr(analytics, old_field):
                update_fields[old_field] = F(old_field) - 1

        # Increment new status count
        new_field = f"rsvp_{new_status}_count"
        if hasattr(analytics, new_field):
            update_fields[new_field] = F(new_field) + 1

        # Increment total changes
        update_fields['rsvp_changes'] = F('rsvp_changes') + 1

        # Apply updates
        for field, value in update_fields.items():
            setattr(analytics, field, value)

        analytics.save(update_fields=update_fields.keys())
        analytics.refresh_from_db()  # to reflect F() results

        return analytics

    @staticmethod
    def get_event_summary(event: Event, days: int = 30) -> dict:
        """Get summary analytics for an event over the last N days."""
        start_date = timezone.now().date() - datetime.timedelta(days=days)
        records = EventAnalytics.objects.filter(
            event=event,
            date__gte=start_date
        ).order_by('date')

        total_changes = sum(r.rsvp_changes for r in records)
        avg_changes_per_day = total_changes / days if days else 0

        # Current counts (latest record or zero)
        latest = records.last()
        current_counts = {
            'going': latest.rsvp_going_count if latest else 0,
            'maybe': latest.rsvp_maybe_count if latest else 0,
            'declined': latest.rsvp_declined_count if latest else 0,
        }

        return {
            'event_id': event.id,
            'period_days': days,
            'total_rsvp_changes': total_changes,
            'avg_changes_per_day': avg_changes_per_day,
            'current_rsvp_counts': current_counts,
            'daily_breakdown': [
                {
                    'date': r.date,
                    'going': r.rsvp_going_count,
                    'maybe': r.rsvp_maybe_count,
                    'declined': r.rsvp_declined_count,
                    'changes': r.rsvp_changes,
                }
                for r in records
            ]
        }