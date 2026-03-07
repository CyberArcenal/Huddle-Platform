from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.utils import timezone
import datetime

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from global_utils.pagination import AdminPanelPagination

from ..services.admin_log import AdminLogService
from ..serializers.base import (
    AdminLogSerializer, AdminLogFilterSerializer, AdminStatisticsSerializer,
    BanUserInputSerializer, WarnUserInputSerializer, RemoveContentInputSerializer,
    SearchAdminLogsSerializer
)
from users.models import User


class AdminLogListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='admin_user_id', type=int, description='Filter by admin user ID', required=False),
            OpenApiParameter(name='action', type=str, description='Filter by action type', required=False),
            OpenApiParameter(name='target_user_id', type=int, description='Filter by target user ID', required=False),
            OpenApiParameter(name='start_date', type=str, description='Start date (ISO format)', required=False),
            OpenApiParameter(name='end_date', type=str, description='End date (ISO format)', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: AdminLogSerializer(many=True)},
        description="List admin logs with optional filters and pagination."
    )
    def get(self, request):
        serializer = AdminLogFilterSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        admin_user = None
        if data.get('admin_user_id'):
            admin_user = get_object_or_404(User, id=data['admin_user_id'])
        target_user = None
        if data.get('target_user_id'):
            target_user = get_object_or_404(User, id=data['target_user_id'])

        logs = AdminLogService.get_admin_logs(
            admin_user=admin_user,
            action=data.get('action'),
            target_user=target_user,
            start_date=data.get('start_date'),
            end_date=data.get('end_date')
        )

        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(logs, request)
        log_serializer = AdminLogSerializer(page, many=True)
        return paginator.get_paginated_response(log_serializer.data)


class AdminLogDetailView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        responses={200: AdminLogSerializer},
        description="Retrieve a single admin log by its ID."
    )
    def get(self, request, log_id):
        log = AdminLogService.get_log_by_id(log_id)
        if not log:
            return Response({'error': 'Log not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminLogSerializer(log)
        return Response(serializer.data)


class AdminLogRecentView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='days', type=int, description='Number of days to look back', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: AdminLogSerializer(many=True)},
        description="Get recent admin actions (last N days)."
    )
    def get(self, request):
        days = int(request.query_params.get('days', 7))
        logs = AdminLogService.get_recent_admin_actions(days=days)
        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(logs, request)
        serializer = AdminLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminLogUserView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='as_admin', type=bool, description='Include logs where user acted as admin', required=False),
            OpenApiParameter(name='as_target', type=bool, description='Include logs where user was target', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: AdminLogSerializer(many=True)},
        description="Get admin logs related to a specific user (as admin or target)."
    )
    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        as_admin = request.query_params.get('as_admin', 'false').lower() == 'true'
        as_target = request.query_params.get('as_target', 'true').lower() == 'true'
        logs = AdminLogService.get_user_admin_logs(
            user, as_admin=as_admin, as_target=as_target
        )
        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(logs, request)
        serializer = AdminLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminLogStatisticsView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='admin_user_id', type=int, description='Filter by admin user ID', required=False),
            OpenApiParameter(name='days', type=int, description='Number of days for statistics', required=False),
        ],
        responses={200: AdminStatisticsSerializer},
        description="Get statistics about admin actions."
    )
    def get(self, request):
        admin_user_id = request.query_params.get('admin_user_id')
        days = int(request.query_params.get('days', 30))
        admin_user = None
        if admin_user_id:
            admin_user = get_object_or_404(User, id=admin_user_id)
        stats = AdminLogService.get_admin_statistics(admin_user, days)
        serializer = AdminStatisticsSerializer(stats)
        return Response(serializer.data)


class AdminLogSearchView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='query', type=str, description='Search query', required=True),
            OpenApiParameter(name='search_in', type=str, description='Fields to search in (comma-separated)', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: AdminLogSerializer(many=True)},
        description="Search admin logs by query."
    )
    def get(self, request):
        serializer = SearchAdminLogsSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        logs = AdminLogService.search_admin_logs(
            query=data['query'],
            search_in=data.get('search_in', ['reason'])
        )
        paginator = AdminPanelPagination()
        page = paginator.paginate_queryset(logs, request)
        log_serializer = AdminLogSerializer(page, many=True)
        return paginator.get_paginated_response(log_serializer.data)


class AdminLogExportView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='start_date', type=str, description='Start date (ISO format)', required=False),
            OpenApiParameter(name='end_date', type=str, description='End date (ISO format)', required=False),
            OpenApiParameter(name='format', type=str, description='Export format (json)', required=False),
        ],
        responses={200: {'type': 'object'}},
        description="Export admin logs as JSON."
    )
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        fmt = request.query_params.get('format', 'json')

        try:
            if start_date:
                start_date = datetime.datetime.fromisoformat(start_date)
            if end_date:
                end_date = datetime.datetime.fromisoformat(end_date)
        except ValueError:
            return Response({'error': 'Invalid date format. Use ISO format.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            data = AdminLogService.export_admin_logs(start_date, end_date, fmt)
            return Response(data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminLogCleanupView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request={'application/json': {'days_to_keep': 365}},
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}},
        description="Delete old admin logs (older than given days)."
    )
    def post(self, request):
        days_to_keep = int(request.data.get('days_to_keep', 365))
        count = AdminLogService.cleanup_old_logs(days_to_keep)
        return Response({'message': f'Deleted {count} old admin logs.'})


# ---------- Action Views ----------
class AdminBanUserView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=BanUserInputSerializer,
        responses={200: {'type': 'object'}},
        examples=[
            OpenApiExample(
                'Ban request',
                value={
                    'user_id': 42,
                    'reason': 'Violation of community guidelines',
                    'duration_days': 7
                },
                request_only=True
            ),
            OpenApiExample(
                'Ban response',
                value={
                    'user_id': 42,
                    'username': 'offender',
                    'previous_status': 'active',
                    'new_status': 'suspended',
                    'duration_days': 7,
                    'banned_at': '2025-03-07T12:34:56Z',
                    'banned_by': 'admin',
                    'reason': 'Violation of community guidelines'
                },
                response_only=True
            )
        ],
        description="Ban a user."
    )
    def post(self, request):
        serializer = BanUserInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        target_user = get_object_or_404(User, id=data['user_id'])

        try:
            log, result = AdminLogService.ban_user(
                admin_user=request.user,
                target_user=target_user,
                reason=data['reason'],
                duration_days=data.get('duration_days')
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminWarnUserView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=WarnUserInputSerializer,
        responses={200: {'type': 'object'}},
        examples=[
            OpenApiExample(
                'Warn request',
                value={
                    'user_id': 42,
                    'reason': 'Spamming',
                    'severity': 'medium'
                },
                request_only=True
            ),
            OpenApiExample(
                'Warn response',
                value={
                    'user_id': 42,
                    'username': 'offender',
                    'warning_severity': 'medium',
                    'warned_at': '2025-03-07T12:34:56Z',
                    'warned_by': 'admin',
                    'reason': 'Spamming',
                    'warning_count': 2
                },
                response_only=True
            )
        ],
        description="Warn a user."
    )
    def post(self, request):
        serializer = WarnUserInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        target_user = get_object_or_404(User, id=data['user_id'])

        try:
            log, result = AdminLogService.warn_user(
                admin_user=request.user,
                target_user=target_user,
                reason=data['reason'],
                severity=data.get('severity', 'low')
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminRemoveContentView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=RemoveContentInputSerializer,
        responses={200: {'type': 'object'}},
        examples=[
            OpenApiExample(
                'Remove content request',
                value={
                    'content_type': 'post',
                    'object_id': 123,
                    'reason': 'Inappropriate content'
                },
                request_only=True
            ),
            OpenApiExample(
                'Remove content response',
                value={
                    'content_type': 'post',
                    'object_id': 123,
                    'removed_at': '2025-03-07T12:34:56Z',
                    'removed_by': 'admin',
                    'reason': 'Inappropriate content'
                },
                response_only=True
            )
        ],
        description="Remove a piece of content (post or group)."
    )
    def post(self, request):
        serializer = RemoveContentInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            log, result = AdminLogService.remove_content(
                admin_user=request.user,
                content_type=data['content_type'],
                object_id=data['object_id'],
                reason=data['reason']
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)