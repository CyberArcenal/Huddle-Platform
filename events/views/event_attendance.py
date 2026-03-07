from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from events.serializers.event import EventListSerializer
from events.serializers.event_attendance import (
    EventAttendanceWithUserSerializer,
    UserAttendanceStatisticsSerializer,
)
from global_utils.pagination import EventsPagination

from ..models import Event, EventAttendance
from ..serializers import (
    EventAttendanceSerializer,
    EventAttendanceCreateSerializer,
    EventAttendanceUpdateSerializer,
)
from ..services import EventAttendanceService, EventService
from users.models import User
from groups.services import GroupMemberService


class EventAttendanceListView(APIView):
    """List attendees for an event"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='status', type=str, description='Filter by status (going, maybe, declined)', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: EventAttendanceWithUserSerializer(many=True)},
        description="List all attendees for an event, optionally filtered by status."
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, id=event_id)

        has_access, message = EventService.check_user_access(event, request.user)
        if not has_access:
            raise PermissionDenied(detail=message)

        status_filter = request.query_params.get("status")

        # Service returns full queryset
        attendees = EventAttendanceService.get_event_attendees(
            event=event, status=status_filter
        )

        paginator = EventsPagination()
        page = paginator.paginate_queryset(attendees, request)
        serializer = EventAttendanceWithUserSerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=EventAttendanceCreateSerializer,
        responses={201: EventAttendanceSerializer},
        examples=[
            OpenApiExample(
                'RSVP request',
                value={
                    'status': 'going'
                },
                request_only=True
            ),
            OpenApiExample(
                'RSVP response',
                value={
                    'id': 1,
                    'event': 1,
                    'user': 5,
                    'status': 'going',
                    'joined_at': '2025-03-07T12:34:56Z'
                },
                response_only=True
            )
        ],
        description="RSVP to an event (create attendance)."
    )
    def post(self, request, event_id):
        """RSVP to an event"""
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        # Add event to request data
        data = request.data.copy()
        data["event"] = event.id

        serializer = EventAttendanceCreateSerializer(
            data=data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                attendance = serializer.save()
                return Response(
                    EventAttendanceSerializer(
                        attendance, context={"request": request}
                    ).data,
                    status=status.HTTP_201_CREATED,
                )
            except DjangoValidationError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EventAttendanceDetailView(APIView):
    """Retrieve, update or delete an attendance record"""

    permission_classes = [IsAuthenticated]

    def get_object(self, event_id, user_id=None):
        """Get attendance object"""
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        if user_id is None:
            # Get current user's attendance
            user = self.request.user
        else:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise NotFound(detail="User not found")

        attendance = EventAttendanceService.get_attendance(event, user)
        if not attendance:
            raise NotFound(detail="Attendance record not found")

        return attendance

    @extend_schema(
        responses={200: EventAttendanceSerializer},
        description="Retrieve a specific attendance record."
    )
    def get(self, request, event_id, user_id=None):
        """Get attendance record"""
        attendance = self.get_object(event_id, user_id)

        # Check permission (user can view their own or organizer can view any)
        if (
            attendance.user != request.user
            and attendance.event.organizer != request.user
        ):
            raise PermissionDenied(
                detail="You don't have permission to view this attendance"
            )

        serializer = EventAttendanceSerializer(attendance, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=EventAttendanceUpdateSerializer,
        responses={200: EventAttendanceSerializer},
        examples=[
            OpenApiExample(
                'Update status',
                value={'status': 'maybe'},
                request_only=True
            )
        ],
        description="Update attendance status (full update)."
    )
    def put(self, request, event_id, user_id=None):
        """Update attendance status"""
        attendance = self.get_object(event_id, user_id)

        # Check permission (user can update their own)
        if attendance.user != request.user:
            raise PermissionDenied(detail="You can only update your own attendance")

        serializer = EventAttendanceUpdateSerializer(
            attendance, data=request.data, partial=False, context={"request": request}
        )

        if serializer.is_valid():
            try:
                serializer.save()
                return Response(serializer.data)
            except DjangoValidationError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=EventAttendanceUpdateSerializer,
        responses={200: EventAttendanceSerializer},
        examples=[
            OpenApiExample(
                'Update status',
                value={'status': 'declined'},
                request_only=True
            )
        ],
        description="Partially update attendance status."
    )
    def patch(self, request, event_id, user_id=None):
        """Partial update attendance status"""
        attendance = self.get_object(event_id, user_id)

        # Check permission (user can update their own)
        if attendance.user != request.user:
            raise PermissionDenied(detail="You can only update your own attendance")

        serializer = EventAttendanceUpdateSerializer(
            attendance, data=request.data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            try:
                serializer.save()
                return Response(serializer.data)
            except DjangoValidationError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={204: None},
        description="Remove attendance (un‑RSVP)."
    )
    def delete(self, request, event_id, user_id=None):
        """Remove attendance/RSVP"""
        attendance = self.get_object(event_id, user_id)

        # Check permission (user can delete their own)
        if attendance.user != request.user:
            raise PermissionDenied(detail="You can only remove your own attendance")

        try:
            EventAttendanceService.remove_attendance(attendance.event, attendance.user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DjangoValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class EventRSVPView(APIView):
    """RSVP to an event (alternative endpoint)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={'application/json': {'status': 'string'}},
        responses={201: EventAttendanceSerializer},
        examples=[
            OpenApiExample(
                'RSVP request',
                value={'status': 'going'},
                request_only=True
            )
        ],
        description="RSVP to an event (create or update attendance)."
    )
    def post(self, request, event_id):
        """RSVP to event"""
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        status = request.data.get("status", "going")

        try:
            created, attendance = EventAttendanceService.rsvp_to_event(
                event=event, user=request.user, status=status
            )

            if created:
                return Response(
                    EventAttendanceSerializer(
                        attendance, context={"request": request}
                    ).data,
                    status=status.HTTP_201_CREATED,
                )
            else:
                return Response(
                    EventAttendanceSerializer(
                        attendance, context={"request": request}
                    ).data,
                    status=status.HTTP_200_OK,
                )
        except DjangoValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UpdateAttendanceStatusView(APIView):
    """Update attendance status (alternative endpoint)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={'application/json': {'status': 'string'}},
        responses={200: EventAttendanceSerializer},
        examples=[
            OpenApiExample(
                'Update request',
                value={'status': 'maybe'},
                request_only=True
            )
        ],
        description="Update attendance status."
    )
    def patch(self, request, event_id):
        """Update attendance status"""
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        new_status = request.data.get("status")

        if not new_status:
            return Response(
                {"error": "Status is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            attendance = EventAttendanceService.update_attendance_status(
                event=event, user=request.user, new_status=new_status
            )

            return Response(
                EventAttendanceSerializer(attendance, context={"request": request}).data
            )
        except DjangoValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserEventsView(APIView):
    """Get events that a user is attending"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='user_id', type=int, description='User ID (optional, defaults to current)', required=False),
            OpenApiParameter(name='status', type=str, description='Filter by RSVP status', required=False),
            OpenApiParameter(name='upcoming_only', type=bool, description='Show only upcoming events', required=False),
            OpenApiParameter(name='start_date', type=str, description='Start date (ISO format)', required=False),
            OpenApiParameter(name='end_date', type=str, description='End date (ISO format)', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: EventListSerializer(many=True)},
        description="Get events a user is attending, with optional filters."
    )
    def get(self, request, user_id=None):
        if user_id is None:
            user_id = request.query_params.get("user_id")

        if not user_id:
            user = request.user
            if not user.is_authenticated:
                raise PermissionDenied(detail="Authentication required")
        else:
            user = get_object_or_404(User, id=user_id)

        status_filter = request.query_params.get("status")
        upcoming_only = (
            request.query_params.get("upcoming_only", "true").lower() == "true"
        )

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        start_date = None
        end_date = None

        if start_date_str:
            try:
                start_date = timezone.datetime.fromisoformat(
                    start_date_str.replace("Z", "+00:00")
                )
            except ValueError:
                return Response(
                    {"error": "Invalid start_date format. Use ISO format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if end_date_str:
            try:
                end_date = timezone.datetime.fromisoformat(
                    end_date_str.replace("Z", "+00:00")
                )
            except ValueError:
                return Response(
                    {"error": "Invalid end_date format. Use ISO format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Service returns full queryset
        events = EventAttendanceService.get_user_events(
            user=user,
            status=status_filter,
            upcoming_only=upcoming_only,
            start_date=start_date,
            end_date=end_date,
        )

        # Filter accessible events
        accessible_events = []
        for event in events:
            has_access, _ = EventService.check_user_access(event, request.user)
            if has_access or event.event_type == "public":
                accessible_events.append(event)

        paginator = EventsPagination()
        page = paginator.paginate_queryset(accessible_events, request)
        from ..serializers import EventListSerializer

        serializer = EventListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class UserAttendanceStatisticsView(APIView):
    """Get user's event attendance statistics"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='user_id', type=int, description='User ID (optional, defaults to current)', required=False),
        ],
        responses={200: UserAttendanceStatisticsSerializer},
        examples=[
            OpenApiExample(
                'Statistics response',
                value={
                    'total_rsvps': 12,
                    'status_breakdown': {'going': 8, 'maybe': 3, 'declined': 1},
                    'upcoming_events': 5,
                    'past_events_attended': 7,
                    'events_organized': 2,
                    'attendance_rate': 87.5
                },
                response_only=True
            )
        ],
        description="Get attendance statistics for a user."
    )
    def get(self, request, user_id=None):
        """Get user's attendance statistics"""
        if user_id is None:
            user_id = request.query_params.get("user_id")

        if not user_id:
            # Get current user's statistics
            user = request.user
            if not user.is_authenticated:
                raise PermissionDenied(detail="Authentication required")
        else:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )

        # Check permission (user can view their own or friends can view)
        if user != request.user:
            # Add friend check here if needed
            raise PermissionDenied(detail="You can only view your own statistics")

        statistics = EventAttendanceService.get_user_attendance_statistics(user)
        serializer = UserAttendanceStatisticsSerializer(statistics)
        return Response(serializer.data)


class MutualAttendeesView(APIView):
    """Get mutual connections attending an event"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: {'type': 'array', 'items': {'type': 'object'}}},
        examples=[
            OpenApiExample(
                'Mutual attendees response',
                value=[
                    {
                        'user': {'id': 2, 'username': 'alice', 'name': 'Alice Smith'},
                        'is_following': True,
                        'is_followed_by': True,
                        'is_mutual': True
                    }
                ],
                response_only=True
            )
        ],
        description="Get list of attendees that the current user has a follow relationship with."
    )
    def get(self, request, event_id):
        """Get mutual attendees for an event"""
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        # Check access
        has_access, message = EventService.check_user_access(event, request.user)
        if not has_access:
            raise PermissionDenied(detail=message)

        mutual_attendees = EventAttendanceService.get_mutual_attendees(
            event, request.user
        )

        # Format response
        formatted_attendees = []
        for attendee in mutual_attendees:
            formatted_attendees.append(
                {
                    "user": {
                        "id": attendee["user"].id,
                        "username": attendee["user"].username,
                        "name": attendee["user"].get_full_name(),
                    },
                    "is_following": attendee["is_following"],
                    "is_followed_by": attendee["is_followed_by"],
                    "is_mutual": attendee["is_mutual"],
                }
            )

        return Response(formatted_attendees)


class AttendanceTrendView(APIView):
    """Get attendance trend for an event"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='hours_before', type=int, description='Hours before event to include', required=False),
        ],
        responses={200: {'type': 'array', 'items': {'type': 'object'}}},
        description="Get RSVP trend (counts per hour) for an event. Only event organizer can access."
    )
    def get(self, request, event_id):
        """Get attendance trend"""
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        # Check if user is organizer
        if event.organizer != request.user:
            raise PermissionDenied(
                detail="Only event organizer can view attendance trend"
            )

        hours_before = int(request.query_params.get("hours_before", 48))

        trend = EventAttendanceService.get_attendance_trend(event, hours_before)
        return Response(trend)


class SendRemindersView(APIView):
    """Send reminders to event attendees"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={'application/json': {'hours_before': 24}},
        responses={200: {'type': 'object'}},
        examples=[
            OpenApiExample(
                'Reminder response',
                value={
                    'event_id': 1,
                    'hours_before': 24,
                    'reminders_sent': 3,
                    'attendees_to_remind': [
                        {'user_id': 5, 'username': 'john', 'email': 'john@example.com'}
                    ]
                },
                response_only=True
            )
        ],
        description="Trigger reminders for attendees. Only event organizer can access."
    )
    def post(self, request, event_id):
        """Send reminders"""
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        # Check if user is organizer
        if event.organizer != request.user:
            raise PermissionDenied(detail="Only event organizer can send reminders")

        hours_before = int(request.data.get("hours_before", 24))

        reminders = EventAttendanceService.send_reminders(event, hours_before)

        # In a real implementation, you would send actual notifications here
        # For now, just return the list of users to remind

        return Response(
            {
                "event_id": event_id,
                "hours_before": hours_before,
                "reminders_sent": len(reminders),
                "attendees_to_remind": [
                    {
                        "user_id": r["user"].id,
                        "username": r["user"].username,
                        "email": r["email"],
                    }
                    for r in reminders
                ],
            }
        )