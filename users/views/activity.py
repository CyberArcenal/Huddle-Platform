from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import UsersPagination
from users.models.base import ACTION_TYPES

from ..services.user_activity import UserActivityService
from ..serializers.activity import (
    UserActivitySerializer,
    ActivitySummarySerializer,
    ActivitySummaryResponseSerializer,
    LogActivityResponseSerializer,
)
from ..models import User, UserActivity
from rest_framework import serializers
from django.db import transaction


# ----- Input serializer for LogActivityView -----
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


# ----- Paginated response serializer -----
class PaginatedUserActivitySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserActivitySerializer(many=True)


class UserActivityListView(APIView):
    """View for listing user activities"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
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
        responses={200: PaginatedUserActivitySerializer},
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
            serializer = UserActivitySerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FollowingActivityView(APIView):
    """View for getting activities from followed users"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
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
        responses={200: PaginatedUserActivitySerializer},
        description="Get a paginated list of activities from users that the current user follows.",
    )
    def get(self, request):
        try:
            activities = UserActivityService.get_following_activities(user=request.user)
            paginator = UsersPagination()
            page = paginator.paginate_queryset(activities, request)
            serializer = UserActivitySerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ActivitySummaryView(APIView):
    """View for getting activity summary/statistics"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: ActivitySummaryResponseSerializer},
        description="Get a summary of the current user's activity (total counts, last activity, breakdown by type).",
    )
    def get(self, request):
        try:
            from django.db.models import Count
            from django.utils import timezone
            from datetime import timedelta

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

            serializer = ActivitySummarySerializer(summary_data)

            return Response({
                "user_id": request.user.id,
                "summary": serializer.data,
            })

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class RecentActivitiesView(APIView):
    """View for getting recent activities across all users"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
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
        responses={200: PaginatedUserActivitySerializer},
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
            serializer = UserActivitySerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LogActivityView(APIView):
    """View for logging user activities (for internal use)"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
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
                    "message": "Activity logged successfully",
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
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
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
                "message": "Activity logged successfully",
                "activity": output_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )