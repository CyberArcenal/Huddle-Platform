from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from global_utils.pagination import AnalyticsPagination
from users.models import User
from ..services.user_analytics import UserAnalyticsService
from ..serializers.base import (
    UserAnalyticsSerializer,
    UserAnalyticsSummarySerializer,
    UserTrendSerializer,
    UserEngagementSerializer,
    UserTopDaySerializer,
    UserCompareSerializer,
)
import datetime


class UserAnalyticsDailyView(APIView):
    """Get daily analytics for a user"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='date', type=str, description='Date in YYYY-MM-DD (default today)', required=False),
        ],
        responses={200: UserAnalyticsSerializer},
        description="Get daily analytics for a user. User ID in URL is optional; defaults to current user."
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            if request.user != target_user and not request.user.is_staff:
                return Response({'error': 'You do not have permission to view this user\'s analytics'},
                                status=status.HTTP_403_FORBIDDEN)
        else:
            target_user = request.user

        date_str = request.query_params.get('date')
        if date_str:
            try:
                date = datetime.date.fromisoformat(date_str)
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            date = timezone.now().date()

        analytics = UserAnalyticsService.get_user_daily_analytics(target_user, date)
        if not analytics:
            analytics = UserAnalyticsService.get_or_create_daily_analytics(target_user, date)

        serializer = UserAnalyticsSerializer(analytics)
        return Response(serializer.data)


class UserAnalyticsRangeView(APIView):
    """Get user analytics within a date range"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='start_date', type=str, description='Start date (YYYY-MM-DD)', required=True),
            OpenApiParameter(name='end_date', type=str, description='End date (YYYY-MM-DD)', required=True),
            OpenApiParameter(name='include_empty_days', type=bool, description='Include days with no data', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: UserAnalyticsSerializer(many=True)},
        description="Get user analytics for a date range, with optional pagination."
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            if request.user != target_user and not request.user.is_staff:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        else:
            target_user = request.user

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

        analytics = UserAnalyticsService.get_user_analytics_range(target_user, start_date, end_date, include_empty)
        paginator = AnalyticsPagination()
        page = paginator.paginate_queryset(analytics, request)
        serializer = UserAnalyticsSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class UserAnalyticsSummaryView(APIView):
    """Get summary of user analytics over a period"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='days', type=int, description='Number of days (default 30)', required=False),
        ],
        responses={200: UserAnalyticsSummarySerializer},
        description="Get a summary of a user's activity over the last N days."
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            if request.user != target_user and not request.user.is_staff:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        else:
            target_user = request.user

        days = int(request.query_params.get('days', 30))
        summary = UserAnalyticsService.get_user_analytics_summary(target_user, days)
        serializer = UserAnalyticsSummarySerializer(summary)
        return Response(serializer.data)


class UserAnalyticsTrendsView(APIView):
    """Get trend data for a specific metric"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='metric', type=str, description='Metric (posts_count, likes_received, comments_received, new_followers, stories_posted)', required=True),
            OpenApiParameter(name='days', type=int, description='Number of days (default 30)', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: UserTrendSerializer(many=True)},
        description="Get daily trend data for a specific metric."
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            if request.user != target_user and not request.user.is_staff:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        else:
            target_user = request.user

        metric = request.query_params.get('metric')
        days = int(request.query_params.get('days', 30))

        if not metric:
            return Response({'error': 'metric parameter is required'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            trends = UserAnalyticsService.get_user_trends(target_user, metric, days)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        paginator = AnalyticsPagination()
        page = paginator.paginate_queryset(trends, request)
        serializer = UserTrendSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class UserAnalyticsEngagementView(APIView):
    """Get engagement metrics for a user"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='days', type=int, description='Number of days (default 7)', required=False),
        ],
        responses={200: UserEngagementSerializer},
        description="Calculate engagement metrics (likes, comments, trend) for a user."
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            if request.user != target_user and not request.user.is_staff:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        else:
            target_user = request.user

        days = int(request.query_params.get('days', 7))
        engagement = UserAnalyticsService.get_user_engagement_metrics(target_user, days)
        serializer = UserEngagementSerializer(engagement)
        return Response(serializer.data)


class UserAnalyticsTopDaysView(APIView):
    """Get top performing days for a user (limited list, not paginated)"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='metric', type=str, description='Metric (likes_received, comments_received, etc.)', required=False),
            OpenApiParameter(name='limit', type=int, description='Number of top days (default 10)', required=False),
        ],
        responses={200: UserTopDaySerializer(many=True)},
        description="Get the top N days for a user based on a specific metric."
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            if request.user != target_user and not request.user.is_staff:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        else:
            target_user = request.user

        metric = request.query_params.get('metric', 'likes_received')
        limit = int(request.query_params.get('limit', 10))

        try:
            top_days = UserAnalyticsService.get_top_performing_days(target_user, metric, limit)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = UserTopDaySerializer(top_days, many=True)
        return Response(serializer.data)


class UserAnalyticsCompareView(APIView):
    """Compare analytics between two users"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='user1_id', type=int, description='First user ID', required=True),
            OpenApiParameter(name='user2_id', type=int, description='Second user ID', required=True),
            OpenApiParameter(name='days', type=int, description='Number of days to compare (default 30)', required=False),
        ],
        responses={200: UserCompareSerializer},
        description="Compare activity metrics of two users over a period."
    )
    def get(self, request):
        user1_id = request.query_params.get('user1_id')
        user2_id = request.query_params.get('user2_id')
        days = int(request.query_params.get('days', 30))

        if not user1_id or not user2_id:
            return Response({'error': 'user1_id and user2_id are required'},
                            status=status.HTTP_400_BAD_REQUEST)

        user1 = get_object_or_404(User, id=user1_id)
        user2 = get_object_or_404(User, id=user2_id)

        comparison = UserAnalyticsService.compare_users_analytics(user1, user2, days)
        serializer = UserCompareSerializer(comparison)
        return Response(serializer.data)


class UserAnalyticsCleanupView(APIView):
    """Delete old user analytics records"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        request={'application/json': {'days_to_keep': 365}},
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}},
        description="Delete user analytics records older than specified days."
    )
    def post(self, request):
        days_to_keep = int(request.data.get('days_to_keep', 365))
        count = UserAnalyticsService.cleanup_old_analytics(days_to_keep)
        return Response({'message': f'Deleted {count} old user analytics records.'})