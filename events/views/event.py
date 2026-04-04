from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.db import transaction
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
    inline_serializer,
)
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

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------


class EventStatusResponseData(serializers.Serializer):
    id = serializers.IntegerField()
    processing = serializers.BooleanField()
    ready = serializers.BooleanField()
    media_urls = serializers.ListField(child=serializers.URLField(), allow_null=True)


class EventStatusResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventStatusResponseData(allow_null=True)


class PaginatedEventListData(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = EventListSerializer(many=True)


class EventListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedEventListData()


class EventCreateResponseData(serializers.Serializer):
    id = serializers.IntegerField()
    processing = serializers.BooleanField()


class EventCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventCreateResponseData(allow_null=True)


class EventDetailResponseData(serializers.Serializer):
    event = EventDetailSerializer()


class EventDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventDetailResponseData()


class EventUpdateResponseData(serializers.Serializer):
    event = EventDetailSerializer()


class EventUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventUpdateResponseData()


class EventDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class EventStatisticsResponseData(serializers.Serializer):
    statistics = EventStatisticsSerializer()


class EventStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventStatisticsResponseData()


class EventTimelineResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventTimelineSerializer(many=True)


class FeaturedEventsResponseData(serializers.Serializer):
    events = EventListSerializer(many=True)


class FeaturedEventsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = FeaturedEventsResponseData()


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_events(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedEventListData.
    """
    serializer = EventListSerializer(page, many=True, context={"request": request})
    data = {
        "page": paginator.page.number,
        "hasNext": paginator.page.has_next(),
        "hasPrev": paginator.page.has_previous(),
        "count": paginator.page.paginator.count,
        "next": paginator.get_next_link(),
        "previous": paginator.get_previous_link(),
        "results": serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------


class EventStatusView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Event"],
        responses={200: EventStatusResponseSerializer},
        description="Check processing status of an event.",
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if event.event_type != "public" and request.user != event.organizer:
            return Response(
                {
                    "status": False,
                    "message": "Forbidden",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        ready = not event.processing and event.media.exists()
        media_urls = []
        if ready:
            media_urls = [
                request.build_absolute_uri(m.file.url) for m in event.media.all()
            ]
        data = {
            "id": event.id,
            "processing": event.processing,
            "ready": ready,
            "media_urls": media_urls,
        }
        return Response(
            {
                "status": True,
                "message": "Event status retrieved.",
                "data": data,
            }
        )


class EventListView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["Event"],
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
        responses={200: EventListResponseSerializer},
        description="List events with optional filters and pagination.",
    )
    def get(self, request):
        event_type = request.query_params.get("type")
        group_id = request.query_params.get("group_id")
        organizer_id = request.query_params.get("organizer_id")
        upcoming = request.query_params.get("upcoming", "true").lower() == "true"
        days_ahead = int(request.query_params.get("days_ahead", 30))

        try:
            if upcoming:
                queryset = Event.objects.filter(
                    start_time__gte=timezone.now()
                ).order_by("start_time")
            else:
                queryset = Event.objects.all().order_by("-created_at")

            if event_type:
                queryset = queryset.filter(event_type=event_type)

            if group_id:
                group = get_object_or_404(Group, id=group_id)
                queryset = queryset.filter(group=group)

            if organizer_id:
                organizer = get_object_or_404(User, id=organizer_id)
                queryset = queryset.filter(organizer=organizer)

            # Filter out processing events for non-owners
            if not (
                request.user.is_authenticated
                and hasattr(queryset, "organizer")
                and queryset.organizer == request.user
            ):
                queryset = queryset.filter(processing=False)

            # Filter accessible events
            accessible_events = []
            for event in queryset:
                has_access, _ = EventService.check_user_access(event, request.user)
                if has_access or event.event_type == "public":
                    accessible_events.append(event)

            paginator = EventsPagination()
            page = paginator.paginate_queryset(accessible_events, request)
            paginated_data = wrap_paginated_events(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Events retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error listing events")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Event"],
        request={"multipart/form-data": EventCreateSerializer},
        responses={
            202: EventCreateResponseSerializer,
            400: EventCreateResponseSerializer,
        },
        description="Create a new event.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = EventCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid(raise_exception=True):
            event = serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Event upload accepted, processing in background.",
                    "data": {
                        "id": event.id,
                        "processing": True,
                    },
                },
                status=status.HTTP_202_ACCEPTED,
            )
        return Response(
            {
                "status": False,
                "message": "Failed to create event.",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class EventDetailView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_object(self, event_id):
        try:
            return Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            raise NotFound(detail="Event not found")

    @extend_schema(
        tags=["Event"],
        responses={200: EventDetailResponseSerializer},
        description="Retrieve detailed information about an event.",
    )
    def get(self, request, event_id):
        event = self.get_object(event_id)
        has_access, message = EventService.check_user_access(event, request.user)
        if not has_access and event.event_type != "public":
            return Response(
                {
                    "status": False,
                    "message": message,
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        data = EventDetailSerializer(event, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Event retrieved.",
                "data": {"event": data},
            }
        )

    @extend_schema(
        tags=["Event"],
        request=EventUpdateSerializer,
        responses={200: EventUpdateResponseSerializer},
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
        event = self.get_object(pk)
        if event.organizer != request.user:
            return Response(
                {
                    "status": False,
                    "message": "Only the event organizer can update the event",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = EventUpdateSerializer(
            event, data=request.data, partial=False, context={"request": request}
        )
        if serializer.is_valid():
            try:
                event = serializer.save()
                data = EventDetailSerializer(event, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Event updated.",
                        "data": {"event": data},
                    }
                )
            except DjangoValidationError as e:
                return Response(
                    {
                        "status": False,
                        "message": "Something went wrong.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return Response(
            {
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        tags=["Event"],
        request=EventUpdateSerializer,
        responses={200: EventUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Partial update", value={"title": "New Title Only"}, request_only=True
            )
        ],
        description="Partially update an event.",
    )
    def patch(self, request, pk):
        event = self.get_object(pk)
        if event.organizer != request.user:
            return Response(
                {
                    "status": False,
                    "message": "Only the event organizer can update the event",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = EventUpdateSerializer(
            event, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            try:
                event = serializer.save()
                data = EventDetailSerializer(event, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Event partially updated.",
                        "data": {"event": data},
                    }
                )
            except DjangoValidationError as e:
                return Response(
                    {
                        "status": False,
                        "message": "Something went wrong.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return Response(
            {
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        tags=["Event"],
        responses={204: EventDeleteResponseSerializer},
        description="Delete an event.",
    )
    @transaction.atomic
    def delete(self, request, pk):
        event = self.get_object(pk)
        if event.organizer != request.user:
            return Response(
                {
                    "status": False,
                    "message": "Only the event organizer can delete the event",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            EventService.delete_event(event, request.user)
            return Response(
                {
                    "status": True,
                    "message": "Event deleted.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class EventCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event"],
        request=EventCreateSerializer,
        responses={
            202: EventCreateResponseSerializer,
            400: EventCreateResponseSerializer,
        },
        description="Create a new event.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = EventCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid(raise_exception=True):
            event = serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Event upload accepted, processing in background.",
                    "data": {
                        "id": event.id,
                        "processing": True,
                    },
                },
                status=status.HTTP_202_ACCEPTED,
            )
        return Response(
            {
                "status": False,
                "message": "Failed to create event.",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class EventUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event"],
        request=EventUpdateSerializer,
        responses={200: EventUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update event", value={"title": "Updated Title"}, request_only=True
            )
        ],
        description="Update an event (full or partial).",
    )
    @transaction.atomic
    def put(self, request, event_id):
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Event not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if event.organizer != request.user:
            return Response(
                {
                    "status": False,
                    "message": "Only the event organizer can update the event",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = EventUpdateSerializer(
            event, data=request.data, partial=False, context={"request": request}
        )
        if serializer.is_valid():
            try:
                serializer.save()
                data = EventDetailSerializer(event, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Event updated.",
                        "data": {"event": data},
                    }
                )
            except DjangoValidationError as e:
                return Response(
                    {
                        "status": False,
                        "message": "Something went wrong.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return Response(
            {
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class EventDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event"],
        responses={204: EventDeleteResponseSerializer},
        description="Delete an event.",
    )
    @transaction.atomic
    def delete(self, request, event_id):
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Event not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if event.organizer != request.user:
            return Response(
                {
                    "status": False,
                    "message": "Only the event organizer can delete the event",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            EventService.delete_event(event, request.user)
            return Response(
                {
                    "status": True,
                    "message": "Event deleted.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class UpcomingEventsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["Event"],
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
        responses={200: EventListResponseSerializer},
        description="Get upcoming events with filters.",
    )
    def get(self, request):
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

        include_processing = request.user.is_authenticated and user == request.user

        events = EventService.get_upcoming_events(
            user=user,
            group=group,
            event_type=event_type,
            days_ahead=days_ahead,
            include_processing=include_processing,
        )

        accessible_events = []
        for event in events:
            has_access, _ = EventService.check_user_access(event, request.user)
            if has_access or event.event_type == "public":
                accessible_events.append(event)

        paginator = EventsPagination()
        page = paginator.paginate_queryset(accessible_events, request)
        paginated_data = wrap_paginated_events(paginator, page, request)

        return Response(
            {
                "status": True,
                "message": "Upcoming events retrieved.",
                "data": paginated_data,
            }
        )


class PastEventsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["Event"],
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
        responses={200: EventListResponseSerializer},
        description="Get past events with filters.",
    )
    def get(self, request):
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
        paginated_data = wrap_paginated_events(paginator, page, request)

        return Response(
            {
                "status": True,
                "message": "Past events retrieved.",
                "data": paginated_data,
            }
        )


class EventSearchView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["Event"],
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
        responses={200: EventListResponseSerializer},
        description="Search events by query, location, date range.",
    )
    def get(self, request):
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
                    {
                        "status": False,
                        "message": "Invalid date format. Use ISO format.",
                        "data": None,
                    },
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
        paginated_data = wrap_paginated_events(paginator, page, request)

        return Response(
            {
                "status": True,
                "message": "Search results.",
                "data": paginated_data,
            }
        )


class FeaturedEventsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["Event"],
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
        responses={200: FeaturedEventsResponseSerializer},
        description="Get featured (most popular) events.",
    )
    def get(self, request):
        min_attendees = int(request.query_params.get("min_attendees", 5))
        days_ahead = int(request.query_params.get("days_ahead", 7))
        limit = min(int(request.query_params.get("limit", 10)), 20)

        events = EventService.get_featured_events(
            min_attendees=min_attendees, days_ahead=days_ahead, limit=limit
        )
        data = EventListSerializer(events, many=True, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Featured events retrieved.",
                "data": {"events": data},
            }
        )


class RecommendedEventsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event"],
        parameters=[
            OpenApiParameter(
                name="limit", type=int, description="Number of results", required=False
            ),
        ],
        responses={200: FeaturedEventsResponseSerializer},
        description="Get personalized event recommendations.",
    )
    def get(self, request):
        limit = min(int(request.query_params.get("limit", 10)), 20)
        events = EventService.get_recommended_events(user=request.user, limit=limit)
        data = EventListSerializer(events, many=True, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Recommended events retrieved.",
                "data": {"events": data},
            }
        )


class EventStatisticsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event"],
        responses={200: EventStatisticsResponseSerializer},
        description="Get detailed statistics for an event (attendee counts, remaining spots, etc.).",
    )
    def get(self, request, event_id):
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Event not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        has_access, message = EventService.check_user_access(event, request.user)
        if not has_access:
            return Response(
                {
                    "status": False,
                    "message": message,
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        statistics = EventService.get_event_statistics(event)
        return Response(
            {
                "status": True,
                "message": "Event statistics retrieved.",
                "data": {"statistics": statistics},
            }
        )


class EventTimelineView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event"],
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
        responses={200: EventTimelineResponseSerializer},
        description="Get a timeline of events within a date range for the current user.",
    )
    def get(self, request):
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if not start_date_str or not end_date_str:
            return Response(
                {
                    "status": False,
                    "message": "Both start_date and end_date are required",
                    "data": None,
                },
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
                {
                    "status": False,
                    "message": "Invalid date format. Use ISO format.",
                    "data": None,
                },
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
        return Response(
            {
                "status": True,
                "message": "Event timeline retrieved.",
                "data": timeline,
            }
        )


class UserOrganizedEventsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["Event"],
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
        responses={200: EventListResponseSerializer},
        description="Get events organized by a specific user.",
    )
    def get(self, request, user_id=None):
        if user_id is None:
            user_id = request.query_params.get("user_id")
        if not user_id:
            return Response(
                {
                    "status": False,
                    "message": "User ID is required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
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
        paginated_data = wrap_paginated_events(paginator, page, request)

        return Response(
            {
                "status": True,
                "message": "User organized events retrieved.",
                "data": paginated_data,
            }
        )


class GroupEventsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event"],
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
        responses={200: EventListResponseSerializer},
        description="Get events for a group (user must be a group member for private groups).",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)

        # Check if user is group member (for private groups)
        if not GroupMemberService.is_member(group, request.user):
            return Response(
                {
                    "status": False,
                    "message": "You must be a group member to view group events",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        upcoming_only = (
            request.query_params.get("upcoming_only", "true").lower() == "true"
        )

        events = EventService.get_group_events(group=group, upcoming_only=upcoming_only)

        paginator = EventsPagination()
        page = paginator.paginate_queryset(events, request)
        paginated_data = wrap_paginated_events(paginator, page, request)

        return Response(
            {
                "status": True,
                "message": "Group events retrieved.",
                "data": paginated_data,
            }
        )


class EventTypeEventsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["Event"],
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
        responses={200: EventListResponseSerializer},
        description="Get events filtered by event type (public, private, group).",
    )
    def get(self, request, event_type):
        valid_types = [choice[0] for choice in Event.EVENT_TYPES]
        if event_type not in valid_types:
            return Response(
                {
                    "status": False,
                    "message": f"Invalid event type. Must be one of: {valid_types}",
                    "data": None,
                },
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
        paginated_data = wrap_paginated_events(paginator, page, request)

        return Response(
            {
                "status": True,
                "message": "Events by type retrieved.",
                "data": paginated_data,
            }
        )
