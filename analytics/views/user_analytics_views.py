from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import serializers
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from analytics.serializers.user_analytics import UserAnalyticsDisplaySerializer
from global_utils.pagination import AnalyticsPagination
from users.models import User
from ..services.user_analytics import UserAnalyticsService
from ..serializers.base import (
    UserAnalyticsSummarySerializer,
    UserTrendSerializer,
    UserEngagementSerializer,
    UserTopDaySerializer,
    UserCompareSerializer,
)
import datetime
import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_user_analytics(paginator, page, request, serializer_class):
    """
    Construct a paginated data dict that matches the expected structure.
    """
    serializer = serializer_class(page, many=True, context={'request': request})
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
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class PaginatedUserAnalyticsSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserAnalyticsDisplaySerializer(many=True)


class UserAnalyticsDailyResponseData(serializers.Serializer):
    analytics = UserAnalyticsDisplaySerializer()


class UserAnalyticsDailyResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserAnalyticsDailyResponseData()


class UserAnalyticsRangeResponseData(serializers.Serializer):
    pagination = PaginatedUserAnalyticsSerializer()


class UserAnalyticsRangeResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserAnalyticsRangeResponseData(allow_null=True)


class UserAnalyticsSummaryResponseData(serializers.Serializer):
    summary = UserAnalyticsSummarySerializer()


class UserAnalyticsSummaryResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserAnalyticsSummaryResponseData()


class PaginatedUserTrendSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserTrendSerializer(many=True)


class UserAnalyticsTrendsResponseData(serializers.Serializer):
    pagination = PaginatedUserTrendSerializer()


class UserAnalyticsTrendsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserAnalyticsTrendsResponseData(allow_null=True)


class UserAnalyticsEngagementResponseData(serializers.Serializer):
    engagement = UserEngagementSerializer()


class UserAnalyticsEngagementResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserAnalyticsEngagementResponseData()


class UserAnalyticsTopDaysResponseData(serializers.Serializer):
    top_days = UserTopDaySerializer(many=True)


class UserAnalyticsTopDaysResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserAnalyticsTopDaysResponseData()


class UserAnalyticsCompareResponseData(serializers.Serializer):
    comparison = UserCompareSerializer()


class UserAnalyticsCompareResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserAnalyticsCompareResponseData()


class UserAnalyticsCleanupResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


# ----------------------------------------------------------------------
# Input serializers for POST endpoints
# ----------------------------------------------------------------------
class CleanupUserAnalyticsInputSerializer(serializers.Serializer):
    days_to_keep = serializers.IntegerField(
        default=365, help_text="Delete records older than this many days"
    )


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class UserAnalyticsDailyView(APIView):
    """Get daily analytics for a user"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Analytic's"],
        parameters=[
            OpenApiParameter(
                name="date",
                type=str,
                description="Date in YYYY-MM-DD (default today)",
                required=False,
            ),
        ],
        responses={200: UserAnalyticsDailyResponseSerializer},
        description="Get daily analytics for a user. User ID in URL is optional; defaults to current user.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                target_user = get_object_or_404(User, id=user_id)
                if request.user != target_user and not request.user.is_staff:
                    return Response(
                        {
                            "status": False,
                            "message": "You do not have permission to view this user's analytics",
                            "data": None,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                target_user = request.user

            date_str = request.query_params.get("date")
            if date_str:
                try:
                    date = datetime.date.fromisoformat(date_str)
                except ValueError:
                    return Response(
                        {
                            "status": False,
                            "message": "Invalid date format. Use YYYY-MM-DD.",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                date = timezone.now().date()

            analytics = UserAnalyticsService.get_user_daily_analytics(target_user, date)
            if not analytics:
                analytics = UserAnalyticsService.get_or_create_daily_analytics(
                    target_user, date
                )

            data = UserAnalyticsDisplaySerializer(analytics).data
            return Response(
                {
                    "status": True,
                    "message": "Daily analytics retrieved.",
                    "data": {"analytics": data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving daily analytics for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserAnalyticsRangeView(APIView):
    """Get user analytics within a date range"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Analytic's"],
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=str,
                description="Start date (YYYY-MM-DD)",
                required=True,
            ),
            OpenApiParameter(
                name="end_date",
                type=str,
                description="End date (YYYY-MM-DD)",
                required=True,
            ),
            OpenApiParameter(
                name="include_empty_days",
                type=bool,
                description="Include days with no data",
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
        responses={200: UserAnalyticsRangeResponseSerializer},
        description="Get user analytics for a date range, with optional pagination.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                target_user = get_object_or_404(User, id=user_id)
                if request.user != target_user and not request.user.is_staff:
                    return Response(
                        {
                            "status": False,
                            "message": "Permission denied",
                            "data": None,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                target_user = request.user

            start_date_str = request.query_params.get("start_date")
            end_date_str = request.query_params.get("end_date")
            include_empty = (
                request.query_params.get("include_empty_days", "false").lower() == "true"
            )

            if not start_date_str or not end_date_str:
                return Response(
                    {
                        "status": False,
                        "message": "start_date and end_date are required",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                start_date = datetime.date.fromisoformat(start_date_str)
                end_date = datetime.date.fromisoformat(end_date_str)
            except ValueError:
                return Response(
                    {
                        "status": False,
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            analytics = UserAnalyticsService.get_user_analytics_range(
                target_user, start_date, end_date, include_empty
            )
            paginator = AnalyticsPagination()
            page = paginator.paginate_queryset(analytics, request)
            paginated_data = wrap_paginated_user_analytics(
                paginator, page, request, UserAnalyticsDisplaySerializer
            )

            return Response(
                {
                    "status": True,
                    "message": "User analytics range retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user analytics range for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserAnalyticsSummaryView(APIView):
    """Get summary of user analytics over a period"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Analytic's"],
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                description="Number of days (default 30)",
                required=False,
            ),
        ],
        responses={200: UserAnalyticsSummaryResponseSerializer},
        description="Get a summary of a user's activity over the last N days.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                target_user = get_object_or_404(User, id=user_id)
                if request.user != target_user and not request.user.is_staff:
                    return Response(
                        {
                            "status": False,
                            "message": "Permission denied",
                            "data": None,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                target_user = request.user

            days = int(request.query_params.get("days", 30))
            summary = UserAnalyticsService.get_user_analytics_summary(target_user, days)
            return Response(
                {
                    "status": True,
                    "message": "User analytics summary retrieved.",
                    "data": {"summary": summary},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user analytics summary for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserAnalyticsTrendsView(APIView):
    """Get trend data for a specific metric"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Analytic's"],
        parameters=[
            OpenApiParameter(
                name="metric",
                type=str,
                description="Metric (posts_count, likes_received, comments_received, new_followers, stories_posted)",
                required=True,
            ),
            OpenApiParameter(
                name="days",
                type=int,
                description="Number of days (default 30)",
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
        responses={200: UserAnalyticsTrendsResponseSerializer},
        description="Get daily trend data for a specific metric.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                target_user = get_object_or_404(User, id=user_id)
                if request.user != target_user and not request.user.is_staff:
                    return Response(
                        {
                            "status": False,
                            "message": "Permission denied",
                            "data": None,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                target_user = request.user

            metric = request.query_params.get("metric")
            days = int(request.query_params.get("days", 30))

            if not metric:
                return Response(
                    {
                        "status": False,
                        "message": "metric parameter is required",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                trends = UserAnalyticsService.get_user_trends(target_user, metric, days)
            except ValidationError as e:
                return Response(
                    {
                        "status": False,
                        "message": "Something went wrong.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            paginator = AnalyticsPagination()
            page = paginator.paginate_queryset(trends, request)
            paginated_data = wrap_paginated_user_analytics(
                paginator, page, request, UserTrendSerializer
            )

            return Response(
                {
                    "status": True,
                    "message": "User trends retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user trends for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserAnalyticsEngagementView(APIView):
    """Get engagement metrics for a user"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Analytic's"],
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                description="Number of days (default 7)",
                required=False,
            ),
        ],
        responses={200: UserAnalyticsEngagementResponseSerializer},
        description="Calculate engagement metrics (likes, comments, trend) for a user.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                target_user = get_object_or_404(User, id=user_id)
                if request.user != target_user and not request.user.is_staff:
                    return Response(
                        {
                            "status": False,
                            "message": "Permission denied",
                            "data": None,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                target_user = request.user

            days = int(request.query_params.get("days", 7))
            engagement = UserAnalyticsService.get_user_engagement_metrics(target_user, days)
            return Response(
                {
                    "status": True,
                    "message": "User engagement metrics retrieved.",
                    "data": {"engagement": engagement},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user engagement metrics for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserAnalyticsTopDaysView(APIView):
    """Get top performing days for a user (limited list, not paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Analytic's"],
        parameters=[
            OpenApiParameter(
                name="metric",
                type=str,
                description="Metric (likes_received, comments_received, etc.)",
                required=False,
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of top days (default 10)",
                required=False,
            ),
        ],
        responses={200: UserAnalyticsTopDaysResponseSerializer},
        description="Get the top N days for a user based on a specific metric.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                target_user = get_object_or_404(User, id=user_id)
                if request.user != target_user and not request.user.is_staff:
                    return Response(
                        {
                            "status": False,
                            "message": "Permission denied",
                            "data": None,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                target_user = request.user

            metric = request.query_params.get("metric", "likes_received")
            limit = int(request.query_params.get("limit", 10))

            try:
                top_days = UserAnalyticsService.get_top_performing_days(
                    target_user, metric, limit
                )
            except ValidationError as e:
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
                    "status": True,
                    "message": "Top performing days retrieved.",
                    "data": {"top_days": top_days},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving top days for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserAnalyticsCompareView(APIView):
    """Compare analytics between two users"""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["User Analytic's"],
        parameters=[
            OpenApiParameter(
                name="user1_id", type=int, description="First user ID", required=True
            ),
            OpenApiParameter(
                name="user2_id", type=int, description="Second user ID", required=True
            ),
            OpenApiParameter(
                name="days",
                type=int,
                description="Number of days to compare (default 30)",
                required=False,
            ),
        ],
        responses={200: UserAnalyticsCompareResponseSerializer},
        description="Compare activity metrics of two users over a period.",
    )
    def get(self, request):
        try:
            user1_id = request.query_params.get("user1_id")
            user2_id = request.query_params.get("user2_id")
            days = int(request.query_params.get("days", 30))

            if not user1_id or not user2_id:
                return Response(
                    {
                        "status": False,
                        "message": "user1_id and user2_id are required",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user1 = get_object_or_404(User, id=user1_id)
            user2 = get_object_or_404(User, id=user2_id)

            comparison = UserAnalyticsService.compare_users_analytics(user1, user2, days)
            return Response(
                {
                    "status": True,
                    "message": "User comparison retrieved.",
                    "data": {"comparison": comparison},
                }
            )
        except Exception as e:
            logger.exception("Error comparing users %s and %s", user1_id, user2_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserAnalyticsCleanupView(APIView):
    """Delete old user analytics records"""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["User Analytic's"],
        request=CleanupUserAnalyticsInputSerializer,
        responses={200: UserAnalyticsCleanupResponseSerializer},
        description="Delete user analytics records older than specified days.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = CleanupUserAnalyticsInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        days_to_keep = serializer.validated_data["days_to_keep"]
        try:
            count = UserAnalyticsService.cleanup_old_analytics(days_to_keep)
            return Response(
                {
                    "status": True,
                    "message": f"Deleted {count} old user analytics records.",
                    "data": None,
                }
            )
        except Exception as e:
            logger.exception("Error cleaning up old user analytics records")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )