from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from events.serializers.event import EventUpdateSerializer
from global_utils.pagination import EventsPagination

from ..models import Event
from ..serializers import (
    EventSerializer,
    EventDetailSerializer,
    EventCreateSerializer,
    EventListSerializer,
    EventStatisticsSerializer,
    EventTimelineSerializer,
)
from ..services import EventService
from users.models import User
from groups.models import Group
from groups.services import GroupMemberService

from rest_framework import serializers


# ----- Paginated response serializer for drf-spectacular -----
class PaginatedEventListSerializer(serializers.Serializer):
    """Matches the custom pagination response from EventsPagination"""

    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = EventListSerializer(many=True)


class EventListView(APIView):
    """List all events or create a new event"""

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="type",
                type=str,
                description="Filter by event type (public, private, group)",
                required=False,
            ),
            OpenApiParameter(
                name="group_id",
                type=int,
                description="Filter by group ID",
                required=False,
            ),
            OpenApiParameter(
                name="organizer_id",
                type=int,
                description="Filter by organizer ID",
                required=False,
            ),
            OpenApiParameter(
                name="upcoming",
                type=bool,
                description="Show only upcoming events",
                required=False,
            ),
            OpenApiParameter(
                name="days_ahead",
                type=int,
                description="Days ahead for upcoming events",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedEventListSerializer},
        description="List events with optional filters and pagination.",
    )
    def get(self, request):
        """Get list of events with filters"""
        # Get query parameters
        event_type = request.query_params.get("type")
        group_id = request.query_params.get("group_id")
        organizer_id = request.query_params.get("organizer_id")
        upcoming = request.query_params.get("upcoming", "true").lower() == "true"
        days_ahead = int(request.query_params.get("days_ahead", 30))

        # Get queryset (no limit/offset)
        if upcoming:
            queryset = Event.objects.filter(start_time__gte=timezone.now()).order_by(
                "start_time"
            )
        else:
            queryset = Event.objects.all().order_by("-created_at")

        # Apply filters
        if event_type:
            queryset = queryset.filter(event_type=event_type)

        if group_id:
            try:
                group = Group.objects.get(id=group_id)
                queryset = queryset.filter(group=group)
            except Group.DoesNotExist:
                return Response(
                    {"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND
                )

        if organizer_id:
            try:
                organizer = User.objects.get(id=organizer_id)
                queryset = queryset.filter(organizer=organizer)
            except User.DoesNotExist:
                return Response(
                    {"error": "Organizer not found"}, status=status.HTTP_404_NOT_FOUND
                )

        # Filter accessible events
        accessible_events = []
        for event in queryset:
            has_access, _ = EventService.check_user_access(event, request.user)
            if has_access or event.event_type == "public":
                accessible_events.append(event)

        # Apply pagination
        paginator = EventsPagination()
        page = paginator.paginate_queryset(accessible_events, request)
        serializer = EventListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=EventCreateSerializer,
        responses={201: EventDetailSerializer},
        examples=[
            OpenApiExample(
                "Create public event",
                value={
                    "title": "Community Meetup",
                    "description": "Monthly gathering",
                    "location": "Central Park",
                    "start_time": "2025-04-01T10:00:00Z",
                    "end_time": "2025-04-01T12:00:00Z",
                    "event_type": "public",
                    "max_attendees": 50,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create group event",
                value={
                    "title": "Group Hike",
                    "description": "Weekend hike",
                    "location": "Mountain Trail",
                    "start_time": "2025-04-02T09:00:00Z",
                    "end_time": "2025-04-02T15:00:00Z",
                    "event_type": "group",
                    "group_id": 5,
                    "max_attendees": 20,
                },
                request_only=True,
            ),
        ],
        description="Create a new event.",
    )
    @transaction.atomic
    def post(self, request):
        """Create a new event"""
        serializer = EventCreateSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                event = serializer.save()
                return Response(
                    EventDetailSerializer(event, context={"request": request}).data,
                    status=status.HTTP_201_CREATED,
                )
            except DjangoValidationError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EventDetailView(APIView):
    """Retrieve, update or delete an event"""

    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_object(self, pk):
        """Get event object or return 404"""
        try:
            return Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

    @extend_schema(
        responses={200: EventDetailSerializer},
        description="Retrieve detailed information about an event.",
    )
    def get(self, request, pk):
        """Retrieve event details"""
        event = self.get_object(pk)

        # Check access
        has_access, message = EventService.check_user_access(event, request.user)
        if not has_access and event.event_type != "public":
            raise PermissionDenied(detail=message)

        serializer = EventDetailSerializer(event, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=EventUpdateSerializer,
        responses={200: EventDetailSerializer},
        examples=[
            OpenApiExample(
                "Full update",
                value={
                    "title": "Updated Title",
                    "description": "New description",
                    "location": "New location",
                    "start_time": "2025-04-01T11:00:00Z",
                    "end_time": "2025-04-01T13:00:00Z",
                    "event_type": "public",
                    "max_attendees": 60,
                },
                request_only=True,
            )
        ],
        description="Update all fields of an event.",
    )
    @transaction.atomic
    def put(self, request, pk):
        """Update event"""
        event = self.get_object(pk)

        # Check if user is organizer
        if event.organizer != request.user:
            raise PermissionDenied(
                detail="Only the event organizer can update the event"
            )

        serializer = EventUpdateSerializer(
            event, data=request.data, partial=False, context={"request": request}
        )

        if serializer.is_valid():
            try:
                event = serializer.save()
                serializer = EventDetailSerializer(event, context={"request": request})
                return Response(serializer.data)
            except DjangoValidationError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=EventUpdateSerializer,
        responses={200: EventDetailSerializer},
        examples=[
            OpenApiExample(
                "Partial update", value={"title": "New Title Only"}, request_only=True
            )
        ],
        description="Partially update an event.",
    )
    def patch(self, request, pk):
        """Partial update event"""
        event = self.get_object(pk)

        # Check if user is organizer
        if event.organizer != request.user:
            raise PermissionDenied(
                detail="Only the event organizer can update the event"
            )

        serializer = EventUpdateSerializer(
            event, data=request.data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            try:
                event = serializer.save()
                serializer = EventDetailSerializer(event, context={"request": request})
                return Response(serializer.data)
            except DjangoValidationError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(responses={204: None}, description="Delete an event.")
    @transaction.atomic
    def delete(self, request, pk):
        """Delete event"""
        event = self.get_object(pk)

        # Check if user is organizer
        if event.organizer != request.user:
            raise PermissionDenied(
                detail="Only the event organizer can delete the event"
            )

        try:
            EventService.delete_event(event, request.user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DjangoValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class EventCreateView(APIView):
    """Create event (alternative endpoint)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=EventCreateSerializer,
        responses={201: EventDetailSerializer},
        examples=[
            OpenApiExample(
                "Create event",
                value={
                    "title": "New Event",
                    "description": "Description",
                    "location": "Somewhere",
                    "start_time": "2025-04-01T10:00:00Z",
                    "end_time": "2025-04-01T12:00:00Z",
                    "event_type": "public",
                    "max_attendees": 30,
                },
                request_only=True,
            )
        ],
        description="Create a new event.",
    )
    @transaction.atomic
    def post(self, request):
        """Create new event"""
        serializer = EventCreateSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                event = serializer.save()
                return Response(
                    EventDetailSerializer(event, context={"request": request}).data,
                    status=status.HTTP_201_CREATED,
                )
            except DjangoValidationError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EventUpdateView(APIView):
    """Update event (alternative endpoint)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=EventSerializer,
        responses={200: EventSerializer},
        examples=[
            OpenApiExample(
                "Update event", value={"title": "Updated Title"}, request_only=True
            )
        ],
        description="Update an event (full or partial).",
    )
    @transaction.atomic
    def put(self, request, pk):
        """Update event"""
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        # Check if user is organizer
        if event.organizer != request.user:
            raise PermissionDenied(
                detail="Only the event organizer can update the event"
            )

        serializer = EventSerializer(
            event, data=request.data, partial=False, context={"request": request}
        )

        if serializer.is_valid():
            try:
                serializer.save()
                return Response(serializer.data)
            except DjangoValidationError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EventDeleteView(APIView):
    """Delete event (alternative endpoint)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None}, description="Delete an event.")
    @transaction.atomic
    def delete(self, request, pk):
        """Delete event"""
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        # Check if user is organizer
        if event.organizer != request.user:
            raise PermissionDenied(
                detail="Only the event organizer can delete the event"
            )

        try:
            EventService.delete_event(event, request.user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DjangoValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UpcomingEventsView(APIView):
    """Get upcoming events"""

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="Filter by user attending/organizing",
                required=False,
            ),
            OpenApiParameter(
                name="group_id", type=int, description="Filter by group", required=False
            ),
            OpenApiParameter(
                name="type", type=str, description="Event type", required=False
            ),
            OpenApiParameter(
                name="days_ahead",
                type=int,
                description="Number of days ahead",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedEventListSerializer},
        description="Get upcoming events with filters.",
    )
    def get(self, request):
        """Get upcoming events with filters"""
        user_id = request.query_params.get("user_id")
        group_id = request.query_params.get("group_id")
        event_type = request.query_params.get("type")
        days_ahead = int(request.query_params.get("days_ahead", 30))

        user = None
        group = None

        if user_id:
            user = get_object_or_404(User, id=user_id)
        if group_id:
            group = get_object_or_404(Group, id=group_id)

        # Service returns full queryset (no limit/offset)
        events = EventService.get_upcoming_events(
            user=user,
            group=group,
            event_type=event_type,
            days_ahead=days_ahead,
        )

        # Filter accessible events
        accessible_events = []
        for event in events:
            has_access, _ = EventService.check_user_access(event, request.user)
            if has_access or event.event_type == "public":
                accessible_events.append(event)

        paginator = EventsPagination()
        page = paginator.paginate_queryset(accessible_events, request)
        serializer = EventListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class PastEventsView(APIView):
    """Get past events"""

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="Filter by user attending/organizing",
                required=False,
            ),
            OpenApiParameter(
                name="group_id", type=int, description="Filter by group", required=False
            ),
            OpenApiParameter(
                name="days_back",
                type=int,
                description="Number of days back",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedEventListSerializer},
        description="Get past events with filters.",
    )
    def get(self, request):
        """Get past events with filters"""
        user_id = request.query_params.get("user_id")
        group_id = request.query_params.get("group_id")
        days_back = int(request.query_params.get("days_back", 365))

        user = None
        group = None

        if user_id:
            user = get_object_or_404(User, id=user_id)
        if group_id:
            group = get_object_or_404(Group, id=group_id)

        events = EventService.get_past_events(
            user=user, group=group, days_back=days_back
        )

        accessible_events = []
        for event in events:
            has_access, _ = EventService.check_user_access(event, request.user)
            if has_access or event.event_type == "public":
                accessible_events.append(event)

        paginator = EventsPagination()
        page = paginator.paginate_queryset(accessible_events, request)
        serializer = EventListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class EventSearchView(APIView):
    """Search events"""

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="q", type=str, description="Search query", required=False
            ),
            OpenApiParameter(
                name="location", type=str, description="Location filter", required=False
            ),
            OpenApiParameter(
                name="type", type=str, description="Event type", required=False
            ),
            OpenApiParameter(
                name="start_date",
                type=str,
                description="Start date (ISO format)",
                required=False,
            ),
            OpenApiParameter(
                name="end_date",
                type=str,
                description="End date (ISO format)",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedEventListSerializer},
        description="Search events by query, location, date range.",
    )
    def get(self, request):
        """Search events"""
        query = request.query_params.get("q", "")
        location = request.query_params.get("location")
        event_type = request.query_params.get("type")

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        date_range = None

        if start_date_str and end_date_str:
            try:
                start_date = timezone.datetime.fromisoformat(
                    start_date_str.replace("Z", "+00:00")
                )
                end_date = timezone.datetime.fromisoformat(
                    end_date_str.replace("Z", "+00:00")
                )
                date_range = (start_date, end_date)
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use ISO format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        events = EventService.search_events(
            query=query,
            location=location,
            date_range=date_range,
            event_type=event_type,
        )

        accessible_events = []
        for event in events:
            has_access, _ = EventService.check_user_access(event, request.user)
            if has_access or event.event_type == "public":
                accessible_events.append(event)

        paginator = EventsPagination()
        page = paginator.paginate_queryset(accessible_events, request)
        serializer = EventListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class FeaturedEventsView(APIView):
    """Get featured events (most popular)"""

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="min_attendees",
                type=int,
                description="Minimum attendees",
                required=False,
            ),
            OpenApiParameter(
                name="days_ahead", type=int, description="Days ahead", required=False
            ),
            OpenApiParameter(
                name="limit", type=int, description="Number of results", required=False
            ),
        ],
        responses={200: EventListSerializer(many=True)},
        description="Get featured (most popular) events.",
    )
    def get(self, request):
        min_attendees = int(request.query_params.get("min_attendees", 5))
        days_ahead = int(request.query_params.get("days_ahead", 7))
        limit = min(int(request.query_params.get("limit", 10)), 20)

        events = EventService.get_featured_events(
            min_attendees=min_attendees, days_ahead=days_ahead, limit=limit
        )
        serializer = EventListSerializer(
            events, many=True, context={"request": request}
        )
        return Response(serializer.data)


class RecommendedEventsView(APIView):
    """Get event recommendations for current user"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="limit", type=int, description="Number of results", required=False
            ),
        ],
        responses={200: EventListSerializer(many=True)},
        description="Get personalized event recommendations.",
    )
    def get(self, request):
        limit = min(int(request.query_params.get("limit", 10)), 20)
        events = EventService.get_recommended_events(user=request.user, limit=limit)
        serializer = EventListSerializer(
            events, many=True, context={"request": request}
        )
        return Response(serializer.data)


class EventStatisticsView(APIView):
    """Get event statistics"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: EventStatisticsSerializer},
        description="Get detailed statistics for an event (attendee counts, remaining spots, etc.).",
    )
    def get(self, request, pk):
        """Get statistics for a specific event"""
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

        # Check access
        has_access, message = EventService.check_user_access(event, request.user)
        if not has_access:
            raise PermissionDenied(detail=message)

        statistics = EventService.get_event_statistics(event)
        serializer = EventStatisticsSerializer(statistics)
        return Response(serializer.data)


class EventTimelineView(APIView):
    """Get event timeline for current user"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=str,
                description="Start date (ISO format)",
                required=True,
            ),
            OpenApiParameter(
                name="end_date",
                type=str,
                description="End date (ISO format)",
                required=True,
            ),
            OpenApiParameter(
                name="include_attending",
                type=bool,
                description="Include events user is attending",
                required=False,
            ),
            OpenApiParameter(
                name="include_organized",
                type=bool,
                description="Include events user organized",
                required=False,
            ),
        ],
        responses={200: EventTimelineSerializer(many=True)},
        description="Get a timeline of events within a date range for the current user.",
    )
    def get(self, request):
        """Get event timeline within date range"""
        # Parse date range
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if not start_date_str or not end_date_str:
            return Response(
                {"error": "Both start_date and end_date are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_date = timezone.datetime.fromisoformat(
                start_date_str.replace("Z", "+00:00")
            )
            end_date = timezone.datetime.fromisoformat(
                end_date_str.replace("Z", "+00:00")
            )
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use ISO format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        include_attending = (
            request.query_params.get("include_attending", "true").lower() == "true"
        )
        include_organized = (
            request.query_params.get("include_organized", "true").lower() == "true"
        )

        timeline = EventService.get_events_timeline(
            user=request.user,
            start_date=start_date,
            end_date=end_date,
            include_attending=include_attending,
            include_organized=include_organized,
        )

        serializer = EventTimelineSerializer(timeline, many=True)
        return Response(serializer.data)


class UserOrganizedEventsView(APIView):
    """Get events organized by a user"""

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (optional, defaults to current user)",
                required=False,
            ),
            OpenApiParameter(
                name="upcoming_only",
                type=bool,
                description="Show only upcoming events",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedEventListSerializer},
        description="Get events organized by a specific user.",
    )
    def get(self, request, user_id=None):
        if user_id is None:
            user_id = request.query_params.get("user_id")
        if not user_id:
            return Response(
                {"error": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        user = get_object_or_404(User, id=user_id)
        upcoming_only = (
            request.query_params.get("upcoming_only", "true").lower() == "true"
        )

        events = EventService.get_user_organized_events(
            user=user, upcoming_only=upcoming_only
        )

        accessible_events = []
        for event in events:
            has_access, _ = EventService.check_user_access(event, request.user)
            if has_access or event.event_type == "public":
                accessible_events.append(event)

        paginator = EventsPagination()
        page = paginator.paginate_queryset(accessible_events, request)
        serializer = EventListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class GroupEventsView(APIView):
    """Get events for a specific group"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="upcoming_only",
                type=bool,
                description="Show only upcoming events",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedEventListSerializer},
        description="Get events for a group (user must be a group member for private groups).",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)

        # Check if user is group member (for private groups)
        if not GroupMemberService.is_member(group, request.user):
            raise PermissionDenied(
                detail="You must be a group member to view group events"
            )

        upcoming_only = (
            request.query_params.get("upcoming_only", "true").lower() == "true"
        )

        events = EventService.get_group_events(group=group, upcoming_only=upcoming_only)

        paginator = EventsPagination()
        page = paginator.paginate_queryset(events, request)
        serializer = EventListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class EventTypeEventsView(APIView):
    """Get events by type"""

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="upcoming_only",
                type=bool,
                description="Show only upcoming events",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedEventListSerializer},
        description="Get events filtered by event type (public, private, group).",
    )
    def get(self, request, event_type):
        valid_types = [choice[0] for choice in Event.EVENT_TYPES]
        if event_type not in valid_types:
            return Response(
                {"error": f"Invalid event type. Must be one of: {valid_types}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        upcoming_only = (
            request.query_params.get("upcoming_only", "true").lower() == "true"
        )

        events = EventService.get_events_by_type(
            event_type=event_type, upcoming_only=upcoming_only
        )

        accessible_events = []
        for event in events:
            has_access, _ = EventService.check_user_access(event, request.user)
            if has_access or event.event_type == "public":
                accessible_events.append(event)

        paginator = EventsPagination()
        page = paginator.paginate_queryset(accessible_events, request)
        serializer = EventListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)
