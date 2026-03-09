from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.utils import timezone
import datetime
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from global_utils.pagination import AdminPanelPagination

from ..services.reported_content import ReportedContentService
from ..serializers.base import (
    ReportedContentSerializer,
    ReportContentInputSerializer,
    ReportFilterSerializer,
    ReportStatusUpdateSerializer,
    ResolveReportInputSerializer,
    ReportStatisticsSerializer,
    SearchAdminLogsSerializer,
    DismissReportInputSerializer,  # <-- new serializer
    CleanupReportsInputSerializer,  # <-- new serializer
)
from users.models import User


# ----- Paginated response serializer for drf-spectacular -----
class PaginatedReportedContentSerializer(serializers.Serializer):
    """Matches the custom pagination response from AdminPanelPagination"""

    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ReportedContentSerializer(many=True)


# --------------------------------------------------------------


class ReportCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ReportContentInputSerializer,
        responses={201: ReportedContentSerializer},
        examples=[
            OpenApiExample(
                "Report request",
                value={
                    "content_type": "post",
                    "object_id": 123,
                    "reason": "Harassment",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Report response",
                value={
                    "id": 1,
                    "reporter": 5,
                    "content_type": "post",
                    "object_id": 123,
                    "reason": "Harassment",
                    "status": "pending",
                    "created_at": "2025-03-07T12:34:56Z",
                    "resolved_at": None,
                },
                response_only=True,
            ),
        ],
        description="Submit a new report for a piece of content.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = ReportContentInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            report = ReportedContentService.report_content(
                reporter=request.user,
                content_type=data["content_type"],
                object_id=data["object_id"],
                reason=data["reason"],
            )
            output_serializer = ReportedContentSerializer(report)
            return Response(output_serializer.data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReportListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="status", type=str, description="Filter by status", required=False
            ),
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Filter by content type",
                required=False,
            ),
            OpenApiParameter(
                name="reporter_id",
                type=int,
                description="Filter by reporter ID",
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
                name="unresolved_only",
                type=bool,
                description="Show only unresolved reports",
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
        responses={200: PaginatedReportedContentSerializer},
        description="List reports with optional filters and pagination.",
    )
    def get(self, request):
        serializer = ReportFilterSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        reporter = None
        if data.get("reporter_id"):
            reporter = get_object_or_404(User, id=data["reporter_id"])

        reports = ReportedContentService.get_reports(
            status=data.get("status"),
            content_type=data.get("content_type"),
            reporter=reporter,
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            unresolved_only=data.get("unresolved_only", True),
        )

        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(reports, request)
        output_serializer = ReportedContentSerializer(page, many=True)
        return paginator.get_paginated_response(output_serializer.data)


class ReportPendingView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Filter by content type",
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
        responses={200: PaginatedReportedContentSerializer},
        description="List all pending reports.",
    )
    def get(self, request):
        content_type = request.query_params.get("content_type")
        reports = ReportedContentService.get_pending_reports(content_type)
        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(reports, request)
        serializer = ReportedContentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ReportDetailView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        responses={200: ReportedContentSerializer},
        description="Retrieve a single report by ID.",
    )
    def get(self, request, report_id):
        report = ReportedContentService.get_report_by_id(report_id)
        if not report:
            return Response(
                {"error": "Report not found"}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = ReportedContentSerializer(report)
        return Response(serializer.data)


class ReportUpdateStatusView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=ReportStatusUpdateSerializer,
        responses={200: ReportedContentSerializer},
        examples=[
            OpenApiExample(
                "Update status request",
                value={"status": "reviewed", "resolution_notes": "Investigating"},
                request_only=True,
            ),
            OpenApiExample(
                "Update status response",
                value={
                    "id": 1,
                    "status": "reviewed",
                    "resolved_at": None,
                    "reporter": 5,
                    "content_type": "post",
                    "object_id": 123,
                    "reason": "Harassment",
                    "created_at": "2025-03-07T12:34:56Z",
                },
                response_only=True,
            ),
        ],
        description="Update the status of a report (e.g., mark as reviewed).",
    )
    def patch(self, request, report_id):
        report = ReportedContentService.get_report_by_id(report_id)
        if not report:
            return Response(
                {"error": "Report not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = ReportStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            updated_report = ReportedContentService.update_report_status(
                report=report,
                new_status=data["status"],
                resolved_by=request.user,
                resolution_notes=data.get("resolution_notes"),
            )
            output_serializer = ReportedContentSerializer(updated_report)
            return Response(output_serializer.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReportResolveView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=ResolveReportInputSerializer,
        responses={200: {"type": "object"}},
        examples=[
            OpenApiExample(
                "Resolve request",
                value={
                    "action": "remove_content",
                    "resolution_details": "Post removed",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Resolve response",
                value={
                    "report": {
                        "id": 1,
                        "status": "resolved",
                        "resolved_at": "2025-03-07T12:34:56Z",
                        "reporter": 5,
                        "content_type": "post",
                        "object_id": 123,
                        "reason": "Harassment",
                        "created_at": "2025-03-07T12:34:56Z",
                    },
                    "action_result": {
                        "success": True,
                        "content_type": "post",
                        "object_id": 123,
                        "action_taken": "remove_content",
                        "resolved_by": "admin",
                        "resolved_at": "2025-03-07T12:34:56Z",
                    },
                },
                response_only=True,
            ),
        ],
        description="Resolve a report by taking an action (remove content, warn user, ban user, or dismiss).",
    )
    @transaction.atomic
    def post(self, request, report_id):
        report = ReportedContentService.get_report_by_id(report_id)
        if not report:
            return Response(
                {"error": "Report not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = ResolveReportInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            resolved_report, action_result = ReportedContentService.resolve_report(
                report=report,
                action_taken=data["action"],
                resolved_by=request.user,
                resolution_details=data.get("resolution_details"),
            )
            return Response(
                {
                    "report": ReportedContentSerializer(resolved_report).data,
                    "action_result": action_result,
                }
            )
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReportDismissView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=DismissReportInputSerializer,  # <-- using dedicated serializer
        responses={200: ReportedContentSerializer},
        examples=[
            OpenApiExample(
                "Dismiss request",
                value={"reason": "Not a violation"},
                request_only=True,
            ),
            OpenApiExample(
                "Dismiss response",
                value={
                    "id": 1,
                    "status": "dismissed",
                    "resolved_at": "2025-03-07T12:34:56Z",
                    "reporter": 5,
                    "content_type": "post",
                    "object_id": 123,
                    "reason": "Harassment",
                    "created_at": "2025-03-07T12:34:56Z",
                },
                response_only=True,
            ),
        ],
        description="Dismiss a report without taking action.",
    )
    @transaction.atomic
    def post(self, request, report_id):
        report = ReportedContentService.get_report_by_id(report_id)
        if not report:
            return Response(
                {"error": "Report not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = DismissReportInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reason = serializer.validated_data["reason"]
        try:
            dismissed_report = ReportedContentService.dismiss_report(
                report=report, dismissed_by=request.user, reason=reason
            )
            output_serializer = ReportedContentSerializer(dismissed_report)
            return Response(output_serializer.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReportStatisticsView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                description="Number of days for statistics",
                required=False,
            ),
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Filter by content type",
                required=False,
            ),
        ],
        responses={200: ReportStatisticsSerializer},
        description="Get statistics about reports (counts by status, type, etc.).",
    )
    def get(self, request):
        days = int(request.query_params.get("days", 30))
        content_type = request.query_params.get("content_type")
        stats = ReportedContentService.get_report_statistics(days, content_type)
        serializer = ReportStatisticsSerializer(stats)
        return Response(serializer.data)


class ReportUrgentView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="threshold",
                type=int,
                description="Minimum number of reports to be considered urgent",
                required=False,
            ),
            OpenApiParameter(
                name="hours",
                type=int,
                description="Lookback period in hours",
                required=False,
            ),
        ],
        responses={200: {"type": "array", "items": {"type": "object"}}},
        description="Get urgent reports (multiple reports on the same content in a short time).",
    )
    def get(self, request):
        threshold = int(request.query_params.get("threshold", 5))
        hours = int(request.query_params.get("hours", 24))
        urgent = ReportedContentService.get_urgent_reports(threshold, hours)
        return Response(urgent)


class ReportUserHistoryView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="as_reporter",
                type=bool,
                description="Include reports made by the user",
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
        responses={200: PaginatedReportedContentSerializer},
        description="Get report history for a specific user.",
    )
    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        as_reporter = request.query_params.get("as_reporter", "true").lower() == "true"
        reports = ReportedContentService.get_user_report_history(user, as_reporter)
        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(reports, request)
        serializer = ReportedContentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ReportSearchView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
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
        responses={200: PaginatedReportedContentSerializer},
        description="Search reports by query (reason, reporter username).",
    )
    def get(self, request):
        serializer = SearchAdminLogsSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        reports = ReportedContentService.search_reports(
            query=data["query"],
            search_in=data.get("search_in", ["reason", "reporter_username"]),
        )
        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(reports, request)
        output_serializer = ReportedContentSerializer(page, many=True)
        return paginator.get_paginated_response(output_serializer.data)


class ReportCleanupView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=CleanupReportsInputSerializer,  # <-- using dedicated serializer
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        description="Delete old resolved/dismissed reports.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = CleanupReportsInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        days_to_keep = serializer.validated_data["days_to_keep"]
        count = ReportedContentService.cleanup_old_reports(days_to_keep)
        return Response({"message": f"Deleted {count} old reports."})


class ReportModerationReportView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
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
        ],
        responses={200: {"type": "object"}},
        description="Generate a moderation report for a given period.",
    )
    def get(self, request):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
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

        report = ReportedContentService.generate_moderation_report(start_date, end_date)
        return Response(report)
