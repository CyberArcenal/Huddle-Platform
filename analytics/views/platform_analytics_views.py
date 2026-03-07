from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from django.utils import timezone
from django.core.exceptions import ValidationError

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from analytics.serializers.base import (
    DailyReportSerializer, PlatformAnalyticsSerializer, PlatformAnalyticsSummarySerializer,
    PlatformCorrelationSerializer, PlatformHealthSerializer, PlatformTopDaySerializer,
    PlatformTrendSerializer
)
from global_utils.pagination import AnalyticsPagination
from ..services.platform_analytics import PlatformAnalyticsService
import datetime


class PlatformAnalyticsDailyView(APIView):
    """Get or create daily platform analytics"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='date', type=str, description='Date in YYYY-MM-DD format (defaults to today)', required=False),
        ],
        responses={200: PlatformAnalyticsSerializer},
        description="Retrieve daily platform analytics for a specific date. If not found, creates a new record with zero values."
    )
    def get(self, request):
        date_str = request.query_params.get('date')
        if date_str:
            try:
                date = datetime.date.fromisoformat(date_str)
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            date = timezone.now().date()

        analytics = PlatformAnalyticsService.get_daily_analytics(date)
        if not analytics:
            analytics = PlatformAnalyticsService.get_or_create_daily_analytics(date)

        serializer = PlatformAnalyticsSerializer(analytics)
        return Response(serializer.data)

    @extend_schema(
        request=PlatformAnalyticsSerializer,
        responses={200: PlatformAnalyticsSerializer},
        examples=[
            OpenApiExample(
                'Update request',
                value={
                    'total_users': 1000,
                    'active_users': 500,
                    'new_posts': 50,
                    'new_groups': 5,
                    'total_messages': 200
                },
                request_only=True
            )
        ],
        description="Manually update daily analytics. Only fields provided will be updated."
    )
    def post(self, request):
        """Manually create or update daily analytics (admin only)"""
        date_str = request.data.get('date')
        if date_str:
            try:
                date = datetime.date.fromisoformat(date_str)
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            date = timezone.now().date()

        analytics = PlatformAnalyticsService.get_or_create_daily_analytics(date)
        # Update fields if provided
        for field in ['total_users', 'active_users', 'new_posts', 'new_groups', 'total_messages']:
            if field in request.data:
                setattr(analytics, field, request.data[field])
        analytics.save()

        serializer = PlatformAnalyticsSerializer(analytics)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PlatformAnalyticsRangeView(APIView):
    """Get platform analytics within a date range"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='start_date', type=str, description='Start date (YYYY-MM-DD)', required=True),
            OpenApiParameter(name='end_date', type=str, description='End date (YYYY-MM-DD)', required=True),
            OpenApiParameter(name='include_empty_days', type=bool, description='Include days with no data', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: PlatformAnalyticsSerializer(many=True)},
        description="Get platform analytics for a date range, with optional pagination."
    )
    def get(self, request):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        include_empty = request.query_params.get('include_empty_days', 'false').lower() == 'true'

        if not start_date_str or not end_date_str:
            return Response({'error': 'start_date and end_date are required'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            start_date = datetime.date.fromisoformat(start_date_str)
            end_date = datetime.date.fromisoformat(end_date_str)
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'},
                            status=status.HTTP_400_BAD_REQUEST)

        analytics = PlatformAnalyticsService.get_analytics_range(start_date, end_date, include_empty)
        paginator = AnalyticsPagination()
        page = paginator.paginate_queryset(analytics, request)
        serializer = PlatformAnalyticsSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class PlatformAnalyticsSummaryView(APIView):
    """Get platform summary over a period"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='days', type=int, description='Number of days to include (default 30)', required=False),
        ],
        responses={200: PlatformAnalyticsSummarySerializer},
        description="Get a summary of platform metrics over the last N days."
    )
    def get(self, request):
        days = int(request.query_params.get('days', 30))
        summary = PlatformAnalyticsService.get_platform_summary(days)
        serializer = PlatformAnalyticsSummarySerializer(summary)
        return Response(serializer.data)


class PlatformAnalyticsTrendsView(APIView):
    """Get trends for a specific metric"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='metric', type=str, description='Metric name (total_users, active_users, new_posts, new_groups, total_messages)', required=True),
            OpenApiParameter(name='days', type=int, description='Number of days (default 30)', required=False),
            OpenApiParameter(name='moving_average', type=int, description='Moving average window size (default 7)', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: PlatformTrendSerializer(many=True)},
        description="Get trend data (daily values with moving average) for a specific metric."
    )
    def get(self, request):
        metric = request.query_params.get('metric')
        days = int(request.query_params.get('days', 30))
        moving_avg = int(request.query_params.get('moving_average', 7))

        if not metric:
            return Response({'error': 'metric parameter is required'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            trends = PlatformAnalyticsService.get_platform_trends(metric, days, moving_avg)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        paginator = AnalyticsPagination()
        page = paginator.paginate_queryset(trends, request)
        serializer = PlatformTrendSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class PlatformAnalyticsHealthView(APIView):
    """Get platform health metrics"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='days', type=int, description='Number of days to evaluate (default 7)', required=False),
        ],
        responses={200: PlatformHealthSerializer},
        description="Calculate overall platform health score based on activity, growth, engagement."
    )
    def get(self, request):
        days = int(request.query_params.get('days', 7))
        health = PlatformAnalyticsService.get_platform_health_metrics(days)
        serializer = PlatformHealthSerializer(health)
        return Response(serializer.data)


class PlatformAnalyticsTopDaysView(APIView):
    """Get top performing days (limited list, not paginated)"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='metric', type=str, description='Metric (active_users, total_users, etc.)', required=False),
            OpenApiParameter(name='limit', type=int, description='Number of top days (default 10)', required=False),
        ],
        responses={200: PlatformTopDaySerializer(many=True)},
        description="Get the top performing days for a given metric."
    )
    def get(self, request):
        metric = request.query_params.get('metric', 'active_users')
        limit = int(request.query_params.get('limit', 10))

        try:
            top_days = PlatformAnalyticsService.get_top_performing_days(metric, limit)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PlatformTopDaySerializer(top_days, many=True)
        return Response(serializer.data)


class PlatformAnalyticsCorrelationView(APIView):
    """Analyze correlation between two metrics"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='metric1', type=str, description='First metric', required=True),
            OpenApiParameter(name='metric2', type=str, description='Second metric', required=True),
            OpenApiParameter(name='days', type=int, description='Number of days to analyze (default 30)', required=False),
        ],
        responses={200: PlatformCorrelationSerializer},
        description="Calculate correlation coefficient between two metrics over a period."
    )
    def get(self, request):
        metric1 = request.query_params.get('metric1')
        metric2 = request.query_params.get('metric2')
        days = int(request.query_params.get('days', 30))

        if not metric1 or not metric2:
            return Response({'error': 'metric1 and metric2 are required'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            correlation = PlatformAnalyticsService.get_correlation_analysis(metric1, metric2, days)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PlatformCorrelationSerializer(correlation)
        return Response(serializer.data)


class PlatformAnalyticsReportView(APIView):
    """Generate daily report"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='date', type=str, description='Date in YYYY-MM-DD (default today)', required=False),
        ],
        responses={200: DailyReportSerializer},
        description="Generate a detailed daily report with changes from previous day."
    )
    def get(self, request):
        date_str = request.query_params.get('date')
        if date_str:
            try:
                date = datetime.date.fromisoformat(date_str)
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            date = timezone.now().date()

        report = PlatformAnalyticsService.generate_daily_report(date)
        serializer = DailyReportSerializer(report)
        return Response(serializer.data)


class PlatformAnalyticsCleanupView(APIView):
    """Delete old analytics records"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        request={'application/json': {'days_to_keep': 730}},
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}},
        description="Delete analytics records older than specified days."
    )
    def post(self, request):
        days_to_keep = int(request.data.get('days_to_keep', 730))
        count = PlatformAnalyticsService.cleanup_old_analytics(days_to_keep)
        return Response({'message': f'Deleted {count} old analytics records.'})