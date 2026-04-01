from rest_framework.views import APIView, Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
import datetime
import logging

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from events.models import Event
from events.models.event_analytics import EventAnalytics
from events.serializers.event_analytics import (
    EventAnalyticsSerializer,
    EventAnalyticsSummarySerializer,
)
from events.services.event_analytics import EventAnalyticsService
from global_utils.pagination import AnalyticsPagination
from rest_framework import serializers
from events.serializers.event_analytics import EventAnalyticsSerializer

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_analytics(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedEventAnalyticsData.
    """
    serializer = EventAnalyticsSerializer(page, many=True, context={'request': request})
    data = {
        'page': paginator.page.number,
        'hasNext': paginator.page.has_next(),
        'hasPrev': paginator.page.has_previous(),
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class PaginatedEventAnalyticsData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = EventAnalyticsSerializer(many=True)


class EventAnalyticsListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedEventAnalyticsData()


class EventAnalyticsDetailResponseData(serializers.Serializer):
    analytics = EventAnalyticsSerializer()


class EventAnalyticsDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventAnalyticsDetailResponseData()


class EventAnalyticsSummaryResponseData(serializers.Serializer):
    summary = EventAnalyticsSummarySerializer()


class EventAnalyticsSummaryResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventAnalyticsSummaryResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class EventAnalyticsListView(APIView):
    """
    List all analytics records for a specific event (paginated).
    Only event organizer or staff can view.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Analytic's"],
        parameters=[
            OpenApiParameter(name='start_date', type=str, description='Start date (YYYY-MM-DD)', required=False),
            OpenApiParameter(name='end_date', type=str, description='End date (YYYY-MM-DD)', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: EventAnalyticsListResponseSerializer},
        description="Retrieve paginated analytics records for an event, optionally filtered by date range."
    )
    def get(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)

            # Permission: only organizer or staff
            if request.user != event.organizer and not request.user.is_staff:
                return Response(
                    {
                        "status": False,
                        "message": "You do not have permission to view analytics for this event.",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Optional date range filtering
            start_date = request.query_params.get("start_date")
            end_date = request.query_params.get("end_date")

            queryset = EventAnalytics.objects.filter(event=event).order_by("-date")

            if start_date:
                try:
                    start_date_obj = datetime.date.fromisoformat(start_date)
                    queryset = queryset.filter(date__gte=start_date_obj)
                except ValueError:
                    return Response(
                        {
                            "status": False,
                            "message": "Invalid start_date format. Use YYYY-MM-DD.",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            if end_date:
                try:
                    end_date_obj = datetime.date.fromisoformat(end_date)
                    queryset = queryset.filter(date__lte=end_date_obj)
                except ValueError:
                    return Response(
                        {
                            "status": False,
                            "message": "Invalid end_date format. Use YYYY-MM-DD.",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            paginator = AnalyticsPagination()
            page = paginator.paginate_queryset(queryset, request)
            paginated_data = wrap_paginated_analytics(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Event analytics retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error listing event analytics for event %s", event_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EventAnalyticsDetailView(APIView):
    """
    Retrieve a specific analytics record by date.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Analytic's"],
        responses={200: EventAnalyticsDetailResponseSerializer},
        description="Retrieve a single analytics record for a specific date."
    )
    def get(self, request, event_id, date):
        try:
            event = get_object_or_404(Event, id=event_id)

            if request.user != event.organizer and not request.user.is_staff:
                return Response(
                    {
                        "status": False,
                        "message": "Permission denied.",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            try:
                date_obj = datetime.date.fromisoformat(date)
            except ValueError:
                return Response(
                    {
                        "status": False,
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            analytics = get_object_or_404(EventAnalytics, event=event, date=date_obj)
            data = EventAnalyticsSerializer(analytics).data
            return Response(
                {
                    "status": True,
                    "message": "Event analytics retrieved.",
                    "data": {"analytics": data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving event analytics for event %s on %s", event_id, date)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EventAnalyticsSummaryView(APIView):
    """
    Get summarized analytics for an event over a period.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Analytic's"],
        parameters=[
            OpenApiParameter(name='days', type=int, description='Number of days to summarize', required=False),
        ],
        responses={200: EventAnalyticsSummaryResponseSerializer},
        examples=[
            OpenApiExample(
                'Summary response',
                value={
                    "status": True,
                    "message": "Event summary retrieved.",
                    "data": {
                        "summary": {
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
                            ]
                        }
                    },
                },
                response_only=True
            )
        ],
        description="Get a summary of RSVP activity over the last N days."
    )
    def get(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)

            if request.user != event.organizer and not request.user.is_staff:
                return Response(
                    {
                        "status": False,
                        "message": "Permission denied.",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            days = int(request.query_params.get("days", 30))
            summary = EventAnalyticsService.get_event_summary(event, days)
            return Response(
                {
                    "status": True,
                    "message": "Event summary retrieved.",
                    "data": {"summary": summary},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving event summary for event %s", event_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )