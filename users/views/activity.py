from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from django.db import transaction

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import UsersPagination
from users.models.utilities import ACTION_TYPES

from ..services.user_activity import UserActivityService
from ..serializers.activity import (
    UserActivitySerializer,
    ActivitySummarySerializer,
)
from ..models import User, UserActivity

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Input serializer for LogActivityView
# ----------------------------------------------------------------------
class LogActivityInputSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=[choice[0] for choice in ACTION_TYPES],
        help_text="Action type",
    )
    description = serializers.CharField(
        required=False, allow_blank=True, help_text="Description"
    )
    location = serializers.CharField(
        required=False, allow_null=True, help_text="Location"
    )
    metadata = serializers.JSONField(
        required=False, default=dict, help_text="Additional metadata"
    )


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_activities(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedActivityData.
    """
    serializer = UserActivitySerializer(page, many=True, context={'request': request})
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

class PaginatedActivityData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserActivitySerializer(many=True)


class ActivityListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedActivityData()


class ActivitySummaryResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()
    summary = ActivitySummarySerializer()


class ActivitySummaryResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ActivitySummaryResponseData()


class LogActivityResponseData(serializers.Serializer):
    activity = UserActivitySerializer()


class LogActivityResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LogActivityResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class UserActivityListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Activity"],
        parameters=[
            OpenApiParameter(
                name="action",
                type=str,
                description="Filter by action type",
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
        responses={200: ActivityListResponseSerializer},
        description="Get a paginated list of the current user's activities, optionally filtered by action.",
    )
    def get(self, request):
        try:
            action = request.query_params.get("action")
            activities = UserActivityService.get_user_activities(
                user=request.user, action=action
            )
            paginator = UsersPagination()
            page = paginator.paginate_queryset(activities, request)
            paginated_data = wrap_paginated_activities(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "User activities retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user activities")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FollowingActivityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Activity"],
        parameters=[
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
        responses={200: ActivityListResponseSerializer},
        description="Get a paginated list of activities from users that the current user follows.",
    )
    def get(self, request):
        try:
            activities = UserActivityService.get_following_activities(user=request.user)
            paginator = UsersPagination()
            page = paginator.paginate_queryset(activities, request)
            paginated_data = wrap_paginated_activities(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Following activities retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving following activities")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ActivitySummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Activity"],
        responses={200: ActivitySummaryResponseSerializer},
        description="Get a summary of the current user's activity (total counts, last activity, breakdown by type).",
    )
    def get(self, request):
        try:
            now = timezone.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = now - timedelta(days=now.weekday())

            total_activities = UserActivity.objects.filter(user=request.user).count()
            last_activity = (
                UserActivity.objects.filter(user=request.user)
                .order_by("-timestamp")
                .first()
            )

            activities_by_type = (
                UserActivity.objects.filter(user=request.user)
                .values("action")
                .annotate(count=Count("id"))
                .order_by("-count")
            )
            activity_types = {item["action"]: item["count"] for item in activities_by_type}

            activities_today = UserActivity.objects.filter(
                user=request.user, timestamp__gte=today_start
            ).count()
            activities_this_week = UserActivity.objects.filter(
                user=request.user, timestamp__gte=week_start
            ).count()

            summary_data = {
                "total_activities": total_activities,
                "last_activity": last_activity.timestamp if last_activity else None,
                "activities_by_type": activity_types,
                "activities_today": activities_today,
                "activities_this_week": activities_this_week,
            }

            return Response(
                {
                    "status": True,
                    "message": "Activity summary retrieved.",
                    "data": {
                        "user_id": request.user.id,
                        "summary": summary_data,
                    },
                }
            )
        except Exception as e:
            logger.exception("Error retrieving activity summary")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RecentActivitiesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Activity"],
        parameters=[
            OpenApiParameter(
                name="action",
                type=str,
                description="Filter by action type",
                required=False,
            ),
            OpenApiParameter(
                name="user_id",
                type=int,
                description="Filter by specific user ID",
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
        responses={200: ActivityListResponseSerializer},
        description="Get recent activities (public or from followed users) with optional filters and pagination.",
    )
    def get(self, request):
        try:
            action = request.query_params.get("action")
            user_id = request.query_params.get("user_id")
            user = None
            if user_id:
                user = get_object_or_404(User, id=user_id)

            activities = UserActivityService.get_recent_activities(
                action=action, user=user
            )
            paginator = UsersPagination()
            page = paginator.paginate_queryset(activities, request)
            paginated_data = wrap_paginated_activities(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Recent activities retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving recent activities")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LogActivityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Activity"],
        request=LogActivityInputSerializer,
        responses={201: LogActivityResponseSerializer},
        examples=[
            OpenApiExample(
                "Log activity request",
                value={
                    "action": "login",
                    "description": "User logged in",
                    "metadata": {"device": "mobile"},
                },
                request_only=True,
            ),
            OpenApiExample(
                "Log activity response",
                value={
                    "status": True,
                    "message": "Activity logged successfully",
                    "data": {
                        "activity": {
                            "id": 1,
                            "user": 1,
                            "action": "login",
                            "description": "User logged in",
                            "ip_address": "192.168.1.1",
                            "user_agent": "Mozilla/5.0",
                            "timestamp": "2025-03-07T12:34:56Z",
                            "location": None,
                            "metadata": {"device": "mobile"},
                        }
                    },
                },
                response_only=True,
            ),
        ],
        description="Log a new activity for the current user. (Internal use, typically called by other services.)",
    )
    @transaction.atomic
    def post(self, request):
        serializer = LogActivityInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        try:
            activity = UserActivityService.log_activity(
                user=request.user,
                action=data["action"],
                description=data.get("description", ""),
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
                location=data.get("location"),
                metadata=data.get("metadata", {}),
            )

            output_serializer = UserActivitySerializer(
                activity, context={"request": request}
            )

            return Response(
                {
                    "status": True,
                    "message": "Activity logged successfully",
                    "data": {"activity": output_serializer.data},
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception("Error logging activity")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )