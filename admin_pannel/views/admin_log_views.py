from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
import datetime

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from admin_pannel.serializers.admin_log import AdminLogDisplaySerializer
from global_utils.pagination import AdminPanelPagination

from ..services.admin_log import AdminLogService
from ..serializers.base import (
    AdminLogFilterSerializer,
    AdminStatisticsSerializer,
    BanUserInputSerializer,
    WarnUserInputSerializer,
    RemoveContentInputSerializer,
    SearchAdminLogsSerializer,
    CleanupLogsInputSerializer,  # <-- new serializer
)
from users.models import User


# ----- Paginated response serializer for drf-spectacular -----
class PaginatedAdminLogSerializer(serializers.Serializer):
    """Matches the custom pagination response from AdminPanelPagination"""

    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = AdminLogDisplaySerializer(many=True)


# --------------------------------------------------------------


class AdminLogListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        parameters=[
            OpenApiParameter(
                name="admin_user_id",
                type=int,
                description="Filter by admin user ID",
                required=False,
            ),
            OpenApiParameter(
                name="action",
                type=str,
                description="Filter by action type",
                required=False,
            ),
            OpenApiParameter(
                name="target_user_id",
                type=int,
                description="Filter by target user ID",
                required=False,
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
        responses={200: PaginatedAdminLogSerializer},
        description="List admin logs with optional filters and pagination.",
    )
    def get(self, request):
        serializer = AdminLogFilterSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        admin_user = None
        if data.get("admin_user_id"):
            admin_user = get_object_or_404(User, id=data["admin_user_id"])
        target_user = None
        if data.get("target_user_id"):
            target_user = get_object_or_404(User, id=data["target_user_id"])

        logs = AdminLogService.get_admin_logs(
            admin_user=admin_user,
            action=data.get("action"),
            target_user=target_user,
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
        )

        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(logs, request)
        log_serializer = AdminLogDisplaySerializer(page, many=True)
        return paginator.get_paginated_response(log_serializer.data)


class AdminLogDetailView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        responses={200: AdminLogDisplaySerializer},
        description="Retrieve a single admin log by its ID.",
    )
    def get(self, request, log_id):
        log = AdminLogService.get_log_by_id(log_id)
        if not log:
            return Response(
                {"error": "Log not found"}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminLogDisplaySerializer(log)
        return Response(serializer.data)


class AdminLogRecentView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                description="Number of days to look back",
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
        responses={200: PaginatedAdminLogSerializer},
        description="Get recent admin actions (last N days).",
    )
    def get(self, request):
        days = int(request.query_params.get("days", 7))
        logs = AdminLogService.get_recent_admin_actions(days=days)
        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(logs, request)
        serializer = AdminLogDisplaySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminLogUserView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        parameters=[
            OpenApiParameter(
                name="as_admin",
                type=bool,
                description="Include logs where user acted as admin",
                required=False,
            ),
            OpenApiParameter(
                name="as_target",
                type=bool,
                description="Include logs where user was target",
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
        responses={200: PaginatedAdminLogSerializer},
        description="Get admin logs related to a specific user (as admin or target).",
    )
    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        as_admin = request.query_params.get("as_admin", "false").lower() == "true"
        as_target = request.query_params.get("as_target", "true").lower() == "true"
        logs = AdminLogService.get_user_admin_logs(
            user, as_admin=as_admin, as_target=as_target
        )
        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(logs, request)
        serializer = AdminLogDisplaySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminLogStatisticsView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        parameters=[
            OpenApiParameter(
                name="admin_user_id",
                type=int,
                description="Filter by admin user ID",
                required=False,
            ),
            OpenApiParameter(
                name="days",
                type=int,
                description="Number of days for statistics",
                required=False,
            ),
        ],
        responses={200: AdminStatisticsSerializer},
        description="Get statistics about admin actions.",
    )
    def get(self, request):
        admin_user_id = request.query_params.get("admin_user_id")
        days = int(request.query_params.get("days", 30))
        admin_user = None
        if admin_user_id:
            admin_user = get_object_or_404(User, id=admin_user_id)
        stats = AdminLogService.get_admin_statistics(admin_user, days)
        serializer = AdminStatisticsSerializer(stats)
        return Response(serializer.data)


class AdminLogSearchView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        parameters=[
            OpenApiParameter(
                name="query", type=str, description="Search query", required=True
            ),
            OpenApiParameter(
                name="search_in",
                type=str,
                description="Fields to search in (comma-separated)",
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
        responses={200: PaginatedAdminLogSerializer},
        description="Search admin logs by query.",
    )
    def get(self, request):
        serializer = SearchAdminLogsSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        logs = AdminLogService.search_admin_logs(
            query=data["query"], search_in=data.get("search_in", ["reason"])
        )
        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(logs, request)
        log_serializer = AdminLogDisplaySerializer(page, many=True)
        return paginator.get_paginated_response(log_serializer.data)



# ------------------ Response Serializers ------------------
class AdminUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()


class TargetUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()


class AdminLogEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    action = serializers.CharField()
    admin_user = AdminUserSerializer(allow_null=True)
    target_user = TargetUserSerializer(allow_null=True)
    target_id = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField()
    created_at = serializers.DateTimeField()


class TimeRangeSerializer(serializers.Serializer):
    start = serializers.CharField(allow_null=True)
    end = serializers.CharField(allow_null=True)


class ExportAdminLogsResponseSerializer(serializers.Serializer):
    exported_at = serializers.DateTimeField()
    total_logs = serializers.IntegerField()
    time_range = TimeRangeSerializer()
    logs = AdminLogEntrySerializer(many=True)


# ------------------ API View ------------------
class AdminLogExportView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        parameters=[
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
                name="format",
                type=str,
                description="Export format (json)",
                required=False,
            ),
        ],
        responses={200: ExportAdminLogsResponseSerializer},
        examples=[
            OpenApiExample(
                "Export logs response",
                value={
                    "exported_at": "2026-03-20T15:30:00Z",
                    "total_logs": 2,
                    "time_range": {
                        "start": "2026-03-01T00:00:00Z",
                        "end": "2026-03-20T00:00:00Z",
                    },
                    "logs": [
                        {
                            "id": 1,
                            "action": "user_ban",
                            "admin_user": {
                                "id": 10,
                                "username": "moderator1",
                                "email": "mod1@example.com",
                            },
                            "target_user": {
                                "id": 42,
                                "username": "offender",
                                "email": "offender@example.com",
                            },
                            "target_id": None,
                            "reason": "Violation of community guidelines",
                            "created_at": "2026-03-19T12:00:00Z",
                        },
                        {
                            "id": 2,
                            "action": "post_remove",
                            "admin_user": {
                                "id": 11,
                                "username": "moderator2",
                                "email": "mod2@example.com",
                            },
                            "target_user": None,
                            "target_id": 123,
                            "reason": "Inappropriate content",
                            "created_at": "2026-03-18T09:30:00Z",
                        },
                    ],
                },
                response_only=True,
            )
        ],
        description="Export admin logs as JSON.",
    )
    def get(self, request):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        fmt = request.query_params.get("format", "json")

        try:
            if start_date:
                start_date = datetime.datetime.fromisoformat(start_date)
            if end_date:
                end_date = datetime.datetime.fromisoformat(end_date)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use ISO format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = AdminLogService.export_admin_logs(start_date, end_date, fmt)
            serializer = ExportAdminLogsResponseSerializer(data)
            return Response(serializer.data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminLogCleanupView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        request=CleanupLogsInputSerializer,  # <-- using dedicated serializer
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        description="Delete old admin logs (older than given days).",
    )
    @transaction.atomic
    def post(self, request):
        serializer = CleanupLogsInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        days_to_keep = serializer.validated_data["days_to_keep"]
        count = AdminLogService.cleanup_old_logs(days_to_keep)
        return Response({"message": f"Deleted {count} old admin logs."})


# ---------- Action Views ----------


# ------------------ Response Serializer ------------------
class BanUserResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    previous_status = serializers.CharField()
    new_status = serializers.CharField()
    duration_days = serializers.IntegerField(allow_null=True)
    banned_at = serializers.DateTimeField()
    banned_by = serializers.CharField()
    reason = serializers.CharField()


# ------------------ API View ------------------
class AdminBanUserView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        request=BanUserInputSerializer,
        responses={200: BanUserResponseSerializer},
        examples=[
            OpenApiExample(
                "Ban request",
                value={
                    "user_id": 42,
                    "reason": "Violation of community guidelines",
                    "duration_days": 7,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Ban response",
                value={
                    "user_id": 42,
                    "username": "offender",
                    "previous_status": "active",
                    "new_status": "suspended",
                    "duration_days": 7,
                    "banned_at": "2025-03-07T12:34:56Z",
                    "banned_by": "admin",
                    "reason": "Violation of community guidelines",
                },
                response_only=True,
            ),
        ],
        description="Ban a user.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = BanUserInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        target_user = get_object_or_404(User, id=data["user_id"])

        try:
            log, result = AdminLogService.ban_user(
                admin_user=request.user,
                target_user=target_user,
                reason=data["reason"],
                duration_days=data.get("duration_days"),
            )
            response_serializer = BanUserResponseSerializer(result)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



# ------------------ Response Serializer ------------------
class WarnUserResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    warning_severity = serializers.CharField()
    warned_at = serializers.DateTimeField()
    warned_by = serializers.CharField()
    reason = serializers.CharField()
    warning_count = serializers.IntegerField()


# ------------------ API View ------------------
class AdminWarnUserView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        request=WarnUserInputSerializer,
        responses={200: WarnUserResponseSerializer},
        examples=[
            OpenApiExample(
                "Warn request",
                value={"user_id": 42, "reason": "Spamming", "severity": "medium"},
                request_only=True,
            ),
            OpenApiExample(
                "Warn response",
                value={
                    "user_id": 42,
                    "username": "offender",
                    "warning_severity": "medium",
                    "warned_at": "2025-03-07T12:34:56Z",
                    "warned_by": "admin",
                    "reason": "Spamming",
                    "warning_count": 2,
                },
                response_only=True,
            ),
        ],
        description="Warn a user.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = WarnUserInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        target_user = get_object_or_404(User, id=data["user_id"])

        try:
            log, result = AdminLogService.warn_user(
                admin_user=request.user,
                target_user=target_user,
                reason=data["reason"],
                severity=data.get("severity", "low"),
            )
            response_serializer = WarnUserResponseSerializer(result)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



# ------------------ Response Serializer ------------------
class RemoveContentResponseSerializer(serializers.Serializer):
    content_type = serializers.CharField()
    object_id = serializers.IntegerField()
    removed_at = serializers.DateTimeField()
    removed_by = serializers.CharField()
    reason = serializers.CharField()


# ------------------ API View ------------------
class AdminRemoveContentView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin Log"],
        request=RemoveContentInputSerializer,
        responses={200: RemoveContentResponseSerializer},
        examples=[
            OpenApiExample(
                "Remove content request",
                value={
                    "content_type": "post",
                    "object_id": 123,
                    "reason": "Inappropriate content",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Remove content response",
                value={
                    "content_type": "post",
                    "object_id": 123,
                    "removed_at": "2025-03-07T12:34:56Z",
                    "removed_by": "admin",
                    "reason": "Inappropriate content",
                },
                response_only=True,
            ),
        ],
        description="Remove a piece of content (post or group).",
    )
    @transaction.atomic
    def post(self, request):
        serializer = RemoveContentInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            log, result = AdminLogService.remove_content(
                admin_user=request.user,
                content_type=data["content_type"],
                object_id=data["object_id"],
                reason=data["reason"],
            )
            response_serializer = RemoveContentResponseSerializer(result)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
