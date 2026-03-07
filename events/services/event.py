from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Q
from typing import Optional, List, Dict, Any, Tuple
import uuid

from groups.models.base import Group
from users.models.base import User
from events.models import Event

class EventService:
    """Service for Event model operations"""
    
    @staticmethod
    def create_event(
        organizer: User,
        title: str,
        description: str,
        location: str,
        start_time: timezone.datetime,
        end_time: timezone.datetime,
        event_type: str = 'public',
        group: Optional[Group] = None,
        max_attendees: Optional[int] = None,
        **extra_fields
    ) -> Event:
        """Create a new event"""
        # Validate event type
        valid_types = [choice[0] for choice in Event.EVENT_TYPES]
        if event_type not in valid_types:
            raise ValidationError(f"Event type must be one of {valid_types}")
        
        # Validate time
        if start_time >= end_time:
            raise ValidationError("End time must be after start time")
        
        if start_time < timezone.now():
            raise ValidationError("Start time cannot be in the past")
        
        # Validate group event
        if event_type == 'group' and not group:
            raise ValidationError("Group events require a group")
        
        if event_type != 'group' and group:
            raise ValidationError("Only group events can be associated with a group")
        
        # Validate max attendees
        if max_attendees is not None and max_attendees <= 0:
            raise ValidationError("Max attendees must be positive")
        
        try:
            with transaction.atomic():
                event = Event.objects.create(
                    organizer=organizer,
                    title=title,
                    description=description,
                    location=location,
                    start_time=start_time,
                    end_time=end_time,
                    event_type=event_type,
                    group=group,
                    max_attendees=max_attendees,
                    **extra_fields
                )
                return event
        except IntegrityError as e:
            raise ValidationError(f"Failed to create event: {str(e)}")
    
    @staticmethod
    def get_event_by_id(event_id: int) -> Optional[Event]:
        """Retrieve event by ID"""
        try:
            return Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return None
    
    @staticmethod
    def update_event(event: Event, update_data: Dict[str, Any], updater: User) -> Event:
        """Update event information"""
        # Check if updater is organizer
        if event.organizer != updater:
            raise ValidationError("Only the event organizer can update the event")
        
        # Check if event has already started
        if event.start_time <= timezone.now():
            raise ValidationError("Cannot update event that has already started")
        
        try:
            with transaction.atomic():
                for field, value in update_data.items():
                    if hasattr(event, field) and field not in ['id', 'organizer', 'created_at']:
                        # Special handling for time fields
                        if field in ['start_time', 'end_time']:
                            # Validate new times
                            if field == 'start_time' and value >= event.end_time:
                                raise ValidationError("Start time must be before end time")
                            elif field == 'end_time' and value <= event.start_time:
                                raise ValidationError("End time must be after start time")
                            elif value < timezone.now():
                                raise ValidationError(f"{field} cannot be in the past")
                        
                        setattr(event, field, value)
                
                event.full_clean()
                event.save()
                return event
        except ValidationError as e:
            raise
    
    @staticmethod
    def delete_event(event: Event, deleter: User) -> bool:
        """Delete an event"""
        # Check if deleter is organizer
        if event.organizer != deleter:
            raise ValidationError("Only the event organizer can delete the event")
        
        try:
            event.delete()
            return True
        except Exception:
            return False
    
    @staticmethod
    def cancel_event(event: Event, reason: Optional[str] = None) -> Event:
        """Cancel an event (soft delete alternative)"""
        # You might want to add a 'cancelled' field to the model
        # For now, we'll just delete it
        raise NotImplementedError("Implement cancellation logic as needed")
    
    @staticmethod
    def get_upcoming_events(
        user: Optional[User] = None,
        group: Optional[Group] = None,
        event_type: Optional[str] = None,
        days_ahead: int = 30,
        limit: int = 50,
        offset: int = 0
    ) -> List[Event]:
        """Get upcoming events"""
        queryset = Event.objects.filter(
            start_time__gte=timezone.now(),
            start_time__lte=timezone.now() + timezone.timedelta(days=days_ahead)
        ).order_by('start_time')
        
        if user:
            # Get events organized by user or events user is attending
            from .event_attendance import EventAttendanceService
            attending_event_ids = EventAttendanceService.get_user_events(
                user=user,
                status='going'
            ).values_list('event_id', flat=True)
            
            queryset = queryset.filter(
                Q(organizer=user) | Q(id__in=attending_event_ids)
            )
        
        if group:
            queryset = queryset.filter(group=group)
        
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        
        return list(queryset[offset:offset + limit])
    
    @staticmethod
    def get_past_events(
        user: Optional[User] = None,
        group: Optional[Group] = None,
        days_back: int = 365,
        limit: int = 50,
        offset: int = 0
    ) -> List[Event]:
        """Get past events"""
        queryset = Event.objects.filter(
            end_time__lt=timezone.now(),
            start_time__gte=timezone.now() - timezone.timedelta(days=days_back)
        ).order_by('-start_time')
        
        if user:
            # Get events organized by user or events user attended
            from .event_attendance import EventAttendanceService
            attended_event_ids = EventAttendanceService.get_user_events(
                user=user,
                status='going'
            ).values_list('event_id', flat=True)
            
            queryset = queryset.filter(
                Q(organizer=user) | Q(id__in=attended_event_ids)
            )
        
        if group:
            queryset = queryset.filter(group=group)
        
        return list(queryset[offset:offset + limit])
    
    @staticmethod
    def get_events_by_type(
        event_type: str,
        upcoming_only: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> List[Event]:
        """Get events by type"""
        queryset = Event.objects.filter(event_type=event_type)
        
        if upcoming_only:
            queryset = queryset.filter(start_time__gte=timezone.now())
        
        return list(queryset.order_by('start_time')[offset:offset + limit])
    
    @staticmethod
    def get_group_events(
        group: Group,
        upcoming_only: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> List[Event]:
        """Get events for a specific group"""
        queryset = Event.objects.filter(group=group)
        
        if upcoming_only:
            queryset = queryset.filter(start_time__gte=timezone.now())
        
        return list(queryset.order_by('start_time')[offset:offset + limit])
    
    @staticmethod
    def get_user_organized_events(
        user: User,
        upcoming_only: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> List[Event]:
        """Get events organized by a user"""
        queryset = Event.objects.filter(organizer=user)
        
        if upcoming_only:
            queryset = queryset.filter(start_time__gte=timezone.now())
        
        return list(queryset.order_by('start_time')[offset:offset + limit])
    
    @staticmethod
    def search_events(
        query: str,
        location: Optional[str] = None,
        date_range: Optional[Tuple[timezone.datetime, timezone.datetime]] = None,
        event_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Event]:
        """Search for events"""
        queryset = Event.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
        
        if location:
            queryset = queryset.filter(location__icontains=location)
        
        if date_range:
            start_date, end_date = date_range
            queryset = queryset.filter(
                start_time__gte=start_date,
                end_time__lte=end_date
            )
        
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        
        # Only show upcoming events in search
        queryset = queryset.filter(start_time__gte=timezone.now())
        
        return list(queryset.order_by('start_time')[offset:offset + limit])
    
    @staticmethod
    def get_featured_events(
        min_attendees: int = 5,
        days_ahead: int = 7,
        limit: int = 10
    ) -> List[Event]:
        """Get featured events (most popular upcoming events)"""
        from django.db.models import Count
        
        time_threshold = timezone.now() + timezone.timedelta(days=days_ahead)
        
        featured_events = Event.objects.filter(
            start_time__gte=timezone.now(),
            start_time__lte=time_threshold
        ).annotate(
            attendee_count=Count('attendances', filter=Q(attendances__status='going'))
        ).filter(
            attendee_count__gte=min_attendees
        ).order_by('-attendee_count', 'start_time')[:limit]
        
        return list(featured_events)
    
    @staticmethod
    def get_recommended_events(
        user: User,
        limit: int = 10
    ) -> List[Event]:
        """Get event recommendations for a user"""
        from groups.services import GroupMemberService
        from .event_attendance import EventAttendanceService
        
        # Get groups user is member of
        user_groups = GroupMemberService.get_user_groups(user)
        
        # Get events from user's groups
        group_events = Event.objects.filter(
            group__in=user_groups,
            start_time__gte=timezone.now(),
            event_type='group'
        ).exclude(
            organizer=user  # Exclude events user organized
        ).order_by('start_time')[:limit]
        
        # Get public events with many attendees (popular events)
        if len(group_events) < limit:
            remaining = limit - len(group_events)
            public_events = Event.objects.filter(
                event_type='public',
                start_time__gte=timezone.now()
            ).exclude(
                organizer=user
            ).order_by('start_time')[:remaining]
            
            group_events = list(group_events) + list(public_events)
        
        return group_events[:limit]
    
    @staticmethod
    def is_event_full(event: Event) -> bool:
        """Check if event has reached maximum capacity"""
        if event.max_attendees is None:
            return False
        
        from .event_attendance import EventAttendanceService
        going_count = EventAttendanceService.get_attendance_count(event, status='going')
        
        return going_count >= event.max_attendees
    
    @staticmethod
    def get_event_statistics(event: Event) -> Dict[str, Any]:
        """Get statistics for an event"""
        from .event_attendance import EventAttendanceService
        
        attendance_stats = EventAttendanceService.get_attendance_statistics(event)
        
        return {
            'total_attendees': attendance_stats['total'],
            'going_count': attendance_stats['going'],
            'maybe_count': attendance_stats['maybe'],
            'declined_count': attendance_stats['declined'],
            'is_full': EventService.is_event_full(event),
            'remaining_spots': (
                event.max_attendees - attendance_stats['going']
                if event.max_attendees else None
            ),
            'days_until_event': (event.start_time - timezone.now()).days,
            'duration_hours': (event.end_time - event.start_time).seconds / 3600,
            'organizer': {
                'id': event.organizer.id,
                'username': event.organizer.username
            },
            'group': event.group.name if event.group else None
        }
    
    @staticmethod
    def check_user_access(event: Event, user: User) -> Tuple[bool, str]:
        """Check if user can access/view the event"""
        # Organizer always has access
        if event.organizer == user:
            return True, "Organizer"
        
        # Public events are accessible to everyone
        if event.event_type == 'public':
            return True, "Public event"
        
        # Private events: only invited/attending users
        if event.event_type == 'private':
            from .event_attendance import EventAttendanceService
            if EventAttendanceService.is_user_attending(event, user):
                return True, "Attending private event"
            return False, "Private event - not attending"
        
        # Group events: only group members
        if event.event_type == 'group' and event.group:
            from groups.services import GroupMemberService
            if GroupMemberService.is_member(event.group, user):
                return True, "Group member"
            return False, "Not a group member"
        
        return False, "No access"
    
    @staticmethod
    def get_events_timeline(
        user: User,
        start_date: timezone.datetime,
        end_date: timezone.datetime,
        include_attending: bool = True,
        include_organized: bool = True
    ) -> List[Dict[str, Any]]:
        """Get events timeline for a user within date range"""
        events = []
        
        if include_organized:
            organized_events = Event.objects.filter(
                organizer=user,
                start_time__gte=start_date,
                end_time__lte=end_date
            )
            events.extend(organized_events)
        
        if include_attending:
            from .event_attendance import EventAttendanceService
            attending_events = EventAttendanceService.get_user_events(
                user=user,
                status='going',
                start_date=start_date,
                end_date=end_date
            )
            events.extend(attending_events)
        
        # Remove duplicates and sort
        unique_events = list(set(events))
        unique_events.sort(key=lambda x: x.start_time)
        
        # Format for timeline
        timeline = []
        for event in unique_events:
            timeline.append({
                'event': event,
                'type': 'organized' if event.organizer == user else 'attending',
                'start_time': event.start_time,
                'end_time': event.end_time,
                'duration': event.end_time - event.start_time
            })
        
        return timeline
    
    @staticmethod
    def cleanup_past_events(days_old: int = 365) -> int:
        """Delete events that ended more than specified days ago"""
        time_threshold = timezone.now() - timezone.timedelta(days=days_old)
        
        past_events = Event.objects.filter(end_time__lt=time_threshold)
        count = past_events.count()
        past_events.delete()
        
        return count