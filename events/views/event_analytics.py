from rest_framework.views import APIView, Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
import datetime

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from events.models import Event
from events.models.event_analytics import EventAnalytics
from events.serializers.event_analytics import (
    EventAnalyticsSerializer,
    EventAnalyticsSummarySerializer,
)
from events.services.event_analytics import EventAnalyticsService
from global_utils.pagination import AnalyticsPagination


class EventAnalyticsListView(APIView):
    """
    List all analytics records for a specific event (paginated).
    Only event organizer or staff can view.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='start_date', type=str, description='Start date (YYYY-MM-DD)', required=False),
            OpenApiParameter(name='end_date', type=str, description='End date (YYYY-MM-DD)', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: EventAnalyticsSerializer(many=True)},
        description="Retrieve paginated analytics records for an event, optionally filtered by date range."
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, id=event_id)

        # Permission: only organizer or staff
        if request.user != event.organizer and not request.user.is_staff:
            return Response(
                {
                    "detail": "You do not have permission to view analytics for this event."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Optional date range filtering
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        queryset = EventAnalytics.objects.filter(event=event).order_by("-date")

        if start_date:
            try:
                start_date = datetime.date.fromisoformat(start_date)
                queryset = queryset.filter(date__gte=start_date)
            except ValueError:
                return Response(
                    {"error": "Invalid start_date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if end_date:
            try:
                end_date = datetime.date.fromisoformat(end_date)
                queryset = queryset.filter(date__lte=end_date)
            except ValueError:
                return Response(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        paginator = AnalyticsPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = EventAnalyticsSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class EventAnalyticsDetailView(APIView):
    """
    Retrieve a specific analytics record by date.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: EventAnalyticsSerializer},
        description="Retrieve a single analytics record for a specific date."
    )
    def get(self, request, event_id, date):
        event = get_object_or_404(Event, id=event_id)

        if request.user != event.organizer and not request.user.is_staff:
            return Response(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        try:
            date_obj = datetime.date.fromisoformat(date)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        analytics = get_object_or_404(EventAnalytics, event=event, date=date_obj)
        serializer = EventAnalyticsSerializer(analytics)
        return Response(serializer.data)


class EventAnalyticsSummaryView(APIView):
    """
    Get summarized analytics for an event over a period.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='days', type=int, description='Number of days to summarize', required=False),
        ],
        responses={200: EventAnalyticsSummarySerializer},
        examples=[
            OpenApiExample(
                'Summary response',
                value={
                    'event_id': 1,
                    'period_days': 30,
                    'total_rsvp_changes': 45,
                    'avg_changes_per_day': 1.5,
                    'current_rsvp_counts': {
                        'going': 25,
                        'maybe': 10,
                        'declined': 5
                    },
                    'daily_breakdown': [
                        {'date': '2025-03-01', 'going': 20, 'maybe': 5, 'declined': 2, 'changes': 3},
                        # ...
                    ]
                },
                response_only=True
            )
        ],
        description="Get a summary of RSVP activity over the last N days."
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, id=event_id)

        if request.user != event.organizer and not request.user.is_staff:
            return Response(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        days = int(request.query_params.get("days", 30))
        summary = EventAnalyticsService.get_event_summary(event, days)
        serializer = EventAnalyticsSummarySerializer(summary)
        return Response(serializer.data)