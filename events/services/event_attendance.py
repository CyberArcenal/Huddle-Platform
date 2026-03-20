from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from typing import Optional, List, Dict, Any, Tuple

from events.services.event import EventService
from users.models import User
from ..models import Event, EventAttendance


class EventAttendanceService:
    """Service for EventAttendance model operations"""

    @staticmethod
    def rsvp_to_event(
        event: Event, user: User, status: str = "going"
    ) -> Tuple[bool, Optional[EventAttendance]]:
        """RSVP to an event"""
        # Validate status
        valid_statuses = [choice[0] for choice in EventAttendance.STATUS_CHOICES]
        if status not in valid_statuses:
            raise ValidationError(f"Status must be one of {valid_statuses}")

        # Check if user is organizer (organizer is automatically going)
        if event.organizer == user:
            # Organizer is automatically "going"
            if status != "going":
                raise ValidationError("Event organizer must be 'going'")

        # Check event access
        from .event import EventService

        has_access, message = EventService.check_user_access(event, user)
        if not has_access:
            raise ValidationError(f"Cannot RSVP: {message}")

        # Check if event is full
        if status == "going" and EventService.is_event_full(event):
            raise ValidationError("Event is at full capacity")

        # Check if event has already ended
        if event.end_time < timezone.now():
            raise ValidationError("Cannot RSVP to past event")

        try:
            with transaction.atomic():
                # Check if already RSVPed
                existing = EventAttendanceService.get_attendance(event, user)
                if existing:
                    # Update existing RSVP
                    existing.status = status
                    existing.save()
                    return False, existing  # Updated, not created

                # Create new RSVP
                attendance = EventAttendance.objects.create(
                    event=event, user=user, status=status
                )
                return True, attendance
        except IntegrityError:
            # Race condition: attendance was created concurrently
            return False, EventAttendanceService.get_attendance(event, user)

    @staticmethod
    def update_attendance_status(
        event: Event, user: User, new_status: str
    ) -> EventAttendance:
        """Update attendance status"""
        attendance = EventAttendanceService.get_attendance(event, user)
        if not attendance:
            raise ValidationError("User has not RSVPed to this event")

        # Check if user is organizer
        if event.organizer == user:
            raise ValidationError("Event organizer cannot change RSVP status")

        # Validate status
        valid_statuses = [choice[0] for choice in EventAttendance.STATUS_CHOICES]
        if new_status not in valid_statuses:
            raise ValidationError(f"Status must be one of {valid_statuses}")

        # Check if changing to 'going' when event is full
        if new_status == "going" and attendance.status != "going":
            if EventService.is_event_full(event):
                raise ValidationError("Event is at full capacity")

        attendance.status = new_status
        attendance.save()
        return attendance

    @staticmethod
    def remove_attendance(event: Event, user: User) -> bool:
        """Remove attendance/RSVP"""
        # Organizer cannot remove attendance (they can only delete the event)
        if event.organizer == user:
            raise ValidationError("Event organizer cannot remove their attendance")

        try:
            deleted_count, _ = EventAttendance.objects.filter(
                event=event, user=user
            ).delete()
            return deleted_count > 0
        except Exception:
            return False

    @staticmethod
    def get_attendance(event: Event, user: User) -> Optional[EventAttendance]:
        """Get attendance record for a user"""
        try:
            return EventAttendance.objects.get(event=event, user=user)
        except EventAttendance.DoesNotExist:
            return None

    @staticmethod
    def is_user_attending(event: Event, user: User, status: str = "going") -> bool:
        """Check if user is attending event with specific status"""
        return EventAttendance.objects.filter(
            event=event, user=user, status=status
        ).exists()

    @staticmethod
    def get_event_attendees(
        event: Event, status: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[EventAttendance]:
        """Get all attendees for an event"""
        queryset = EventAttendance.objects.filter(event=event).select_related("user")

        if status:
            queryset = queryset.filter(status=status)

        return list(queryset.order_by("joined_at")[offset : offset + limit])

    @staticmethod
    def get_user_events(
        user: User,
        status: Optional[str] = None,
        upcoming_only: bool = True,
        start_date: Optional[timezone.datetime] = None,
        end_date: Optional[timezone.datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Event]:
        """Get events that a user is attending"""
        attendances = EventAttendance.objects.filter(user=user).select_related("event")

        if status:
            attendances = attendances.filter(status=status)

        if upcoming_only:
            attendances = attendances.filter(event__start_time__gte=timezone.now())

        if start_date:
            attendances = attendances.filter(event__start_time__gte=start_date)

        if end_date:
            attendances = attendances.filter(event__end_time__lte=end_date)

        # Extract events
        events = [
            attendance.event for attendance in attendances.order_by("event__start_time")
        ]

        return events[offset : offset + limit]

    @staticmethod
    def get_attendance_count(event: Event, status: Optional[str] = None) -> int:
        """Get attendance count for an event"""
        queryset = EventAttendance.objects.filter(event=event)

        if status:
            queryset = queryset.filter(status=status)

        return queryset.count()

    @staticmethod
    def get_attendance_statistics(event: Event) -> Dict[str, int]:
        """Get detailed attendance statistics"""
        counts = {}

        for status_choice in EventAttendance.STATUS_CHOICES:
            status = status_choice[0]
            counts[status] = EventAttendance.objects.filter(
                event=event, status=status
            ).count()

        counts["total"] = sum(counts.values())

        return counts

    @staticmethod
    def get_user_attendance_statistics(user: User) -> Dict[str, Any]:
        """Get user's event attendance statistics"""
        all_attendances = EventAttendance.objects.filter(user=user)
        total = all_attendances.count()

        status_counts = {}
        for status_choice in EventAttendance.STATUS_CHOICES:
            status = status_choice[0]
            status_counts[status] = all_attendances.filter(status=status).count()

        # Get upcoming events count
        upcoming = EventAttendance.objects.filter(
            user=user, status="going", event__start_time__gte=timezone.now()
        ).count()

        # Get past events count
        past = EventAttendance.objects.filter(
            user=user, status="going", event__end_time__lt=timezone.now()
        ).count()

        # Get events organized by user
        organized_count = Event.objects.filter(organizer=user).count()

        return {
            "total_rsvps": total,
            "status_breakdown": status_counts,
            "upcoming_events": upcoming,
            "past_events_attended": past,
            "events_organized": organized_count,
            "attendance_rate": (
                (past / organized_count * 100) if organized_count > 0 else 0
            ),
        }

    @staticmethod
    def get_mutual_attendees(event: Event, user: User) -> List[Dict[str, Any]]:
        """Get mutual connections attending the same event"""
        from users.services import UserFollowService

        # Get all attendees
        attendees = EventAttendanceService.get_event_attendees(event, status="going")
        attendee_users = [attendance.user for attendance in attendees]

        # Find which attendees are followed by the user
        mutual_attendees = []
        for attendee in attendee_users:
            if attendee != user:  # Exclude self
                is_following = UserFollowService.is_following(user, attendee)
                is_followed_by = UserFollowService.is_following(attendee, user)

                if is_following or is_followed_by:
                    mutual_attendees.append(
                        {
                            "user": attendee,
                            "is_following": is_following,
                            "is_followed_by": is_followed_by,
                            "is_mutual": is_following and is_followed_by,
                        }
                    )

        return mutual_attendees

    @staticmethod
    def get_attendance_trend(
        event: Event, hours_before: int = 48
    ) -> List[Dict[str, Any]]:
        """Get attendance trend over time"""
        from django.db.models import Count
        from django.db.models.functions import TruncHour

        time_threshold = timezone.now() - timezone.timedelta(hours=hours_before)

        # Group by hour
        trend = (
            EventAttendance.objects.filter(event=event, joined_at__gte=time_threshold)
            .annotate(hour=TruncHour("joined_at"))
            .values("hour")
            .annotate(count=Count("id"))
            .order_by("hour")
        )

        return list(trend)

    @staticmethod
    def send_reminders(event: Event, hours_before: int = 24) -> List[Dict[str, Any]]:
        """Send reminders to event attendees"""
        # This would integrate with your notification system
        # For now, we'll just return a list of attendees to remind

        remind_time = event.start_time - timezone.timedelta(hours=hours_before)

        if timezone.now() >= remind_time:
            # Get attendees who are "going"
            attendees = EventAttendanceService.get_event_attendees(
                event=event, status="going"
            )

            return [
                {
                    "user": attendance.user,
                    "email": attendance.user.email,
                    "status": attendance.status,
                    "reminder_sent": False,  # Placeholder
                }
                for attendance in attendees
            ]

        return []

    @staticmethod
    def cleanup_old_attendances(days_old: int = 365) -> int:
        """Delete attendance records for events that ended long ago"""
        time_threshold = timezone.now() - timezone.timedelta(days=days_old)

        # Get events that ended before threshold
        old_events = Event.objects.filter(end_time__lt=time_threshold)

        # Delete attendances for those events
        old_attendances = EventAttendance.objects.filter(event__in=old_events)
        count = old_attendances.count()
        old_attendances.delete()

        return count
