from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import inline_serializer
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework import serializers
from global_utils.pagination import UsersPagination

from ..services.security_log import SecurityLogService
from ..services.user_security_settings import UserSecuritySettingsService
from ..services.login_session import LoginSessionService
from ..services.blacklisted_access_token import BlacklistedAccessTokenService
from ..serializers.security import (
    ChangePasswordSerializer,
    EnableTwoFactorSerializer,
    DisableTwoFactorSerializer,
    UpdateSecuritySettingsSerializer,
    SecurityLogSerializer,
)
from django.db import transaction
from ..serializers.activity import (
    LoginSessionSerializer,
    TerminateSessionSerializer,
    BulkTerminateSessionsSerializer,
)
from ..models import UserSecuritySettings, SecurityLog, LoginSession
from rest_framework import serializers
from ..serializers.security import SecurityLogSerializer
from ..serializers.activity import LoginSessionSerializer


class PaginatedSecurityLogSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = SecurityLogSerializer(many=True)


class PaginatedLoginSessionSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = LoginSessionSerializer(many=True)


class ChangePasswordView(APIView):
    """View for changing user password"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "user_id": {"type": "integer"},
                },
            }
        },
        examples=[
            OpenApiExample(
                "Change password request",
                value={
                    "old_password": "currentpass",
                    "new_password": "newpass123",
                    "confirm_password": "newpass123",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={"message": "Password changed successfully", "user_id": 1},
                response_only=True,
            ),
        ],
        description="Change the authenticated user's password.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                user = serializer.save()
                return Response(
                    {"message": "Password changed successfully", "user_id": user.id}
                )
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class Enable2FAView(APIView):
    """View for enabling two-factor authentication"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=EnableTwoFactorSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "two_factor_enabled": {"type": "boolean"},
                    "user_id": {"type": "integer"},
                },
            }
        },
        examples=[
            OpenApiExample(
                "Enable 2FA request",
                value={"verification_code": "123456"},
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "message": "Two-factor authentication enabled successfully",
                    "two_factor_enabled": True,
                    "user_id": 1,
                },
                response_only=True,
            ),
        ],
        description="Enable two-factor authentication for the current user.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = EnableTwoFactorSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                settings = serializer.save()
                return Response(
                    {
                        "message": "Two-factor authentication enabled successfully",
                        "two_factor_enabled": settings.two_factor_enabled,
                        "user_id": request.user.id,
                    }
                )
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class Disable2FAView(APIView):
    """View for disabling two-factor authentication"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=DisableTwoFactorSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "two_factor_enabled": {"type": "boolean"},
                    "user_id": {"type": "integer"},
                },
            }
        },
        examples=[
            OpenApiExample(
                "Disable 2FA request",
                value={"verification_code": "123456"},
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "message": "Two-factor authentication disabled successfully",
                    "two_factor_enabled": False,
                    "user_id": 1,
                },
                response_only=True,
            ),
        ],
        description="Disable two-factor authentication for the current user.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = DisableTwoFactorSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                settings = serializer.save()
                return Response(
                    {
                        "message": "Two-factor authentication disabled successfully",
                        "two_factor_enabled": settings.two_factor_enabled,
                        "user_id": request.user.id,
                    }
                )
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class SecuritySettingsView(APIView):
    """View for managing security settings"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: UpdateSecuritySettingsSerializer().data},
        description="Get the current user's security settings.",
    )
    def get(self, request):
        try:
            settings = UserSecuritySettingsService.get_or_create_settings(request.user)
            serializer = UpdateSecuritySettingsSerializer(settings)
            return Response({"user_id": request.user.id, "settings": serializer.data})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=UpdateSecuritySettingsSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "settings": UpdateSecuritySettingsSerializer().data,
                },
            }
        },
        examples=[
            OpenApiExample(
                "Update settings",
                value={
                    "alert_on_new_device": True,
                    "alert_on_password_change": False,
                    "alert_on_failed_login": True,
                },
                request_only=True,
            )
        ],
        description="Update the current user's security settings.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = UpdateSecuritySettingsSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                settings = UserSecuritySettingsService.get_or_create_settings(
                    request.user
                )
                updated_settings = serializer.update(
                    settings, serializer.validated_data
                )
                return Response(
                    {
                        "message": "Security settings updated successfully",
                        "settings": UpdateSecuritySettingsSerializer(
                            updated_settings
                        ).data,
                    }
                )
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class SecurityLogsView(APIView):
    """View for accessing security logs"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="event_type",
                type=str,
                description="Filter by event type",
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
        responses={200: PaginatedSecurityLogSerializer},
        description="Get paginated security logs for the current user.",
    )
    def get(self, request):
        try:
            event_type = request.query_params.get("event_type")
            logs = SecurityLogService.get_user_logs(
                user=request.user, event_type=event_type
            )
            paginator = UsersPagination()
            page = paginator.paginate_queryset(logs, request)
            serializer = SecurityLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FailedLoginAttemptsView(APIView):
    """View for checking failed login attempts"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[...],
        responses={
            200: inline_serializer(
                name="FailedLoginAttemptsResponse",
                fields={
                    "count": serializers.IntegerField(),
                    "hours": serializers.IntegerField(),
                    "attempts": SecurityLogSerializer(many=True).data,
                },
            )
        },
        examples=[
            OpenApiExample(
                "Response",
                value={
                    "count": 3,
                    "hours": 24,
                    "attempts": [
                        {
                            "id": 1,
                            "event_type": "failed_login",
                            "created_at": "2025-03-07T12:34:56Z",
                        },
                        {
                            "id": 2,
                            "event_type": "failed_login",
                            "created_at": "2025-03-07T12:35:10Z",
                        },
                    ],
                },
                response_only=True,
            )
        ],
        description="...",
    )
    def get(self, request):
        try:
            hours = int(request.query_params.get("hours", 24))

            attempts = SecurityLogService.get_failed_login_attempts(
                user=request.user, hours=hours
            )

            count = SecurityLogService.count_failed_login_attempts(
                user=request.user, hours=hours
            )

            serializer = SecurityLogSerializer(attempts, many=True)

            return Response(
                {"count": count, "hours": hours, "attempts": serializer.data}
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SuspiciousActivitiesView(APIView):
    """View for checking suspicious activities"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Maximum number of activities",
                required=False,
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                    "activities": SecurityLogSerializer(many=True).data,
                },
            }
        },
        description="Get suspicious activities flagged for the current user.",
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 20))

            activities = SecurityLogService.get_suspicious_activities(
                user=request.user, limit=limit
            )

            serializer = SecurityLogSerializer(activities, many=True)

            return Response({"count": len(activities), "activities": serializer.data})

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ActiveSessionsView(APIView):
    """View for managing active login sessions"""

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
        responses={200: PaginatedLoginSessionSerializer},
        description="Get all active login sessions for the current user.",
    )
    def get(self, request):
        try:
            sessions = LoginSessionService.get_active_user_sessions(request.user)
            paginator = UsersPagination()
            page = paginator.paginate_queryset(sessions, request)
            serializer = LoginSessionSerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class TerminateSessionView(APIView):
    """View for terminating a specific login session"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=TerminateSessionSerializer,
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        examples=[
            OpenApiExample(
                "Terminate request",
                value={"session_id": "123e4567-e89b-12d3-a456-426614174000"},
                request_only=True,
            )
        ],
        description="Terminate a specific login session by its ID.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = TerminateSessionSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                success = serializer.terminate()
                if success:
                    return Response({"message": "Session terminated successfully"})
                else:
                    return Response(
                        {"error": "Failed to terminate session"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class BulkTerminateSessionsView(APIView):
    """View for terminating multiple sessions"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=BulkTerminateSessionsSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "result": {"type": "object"},
                },
            }
        },
        examples=[
            OpenApiExample(
                "Bulk terminate request",
                value={"session_ids": ["id1", "id2"]},
                request_only=True,
            )
        ],
        description="Terminate multiple sessions at once.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = BulkTerminateSessionsSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                result = serializer.terminate()
                return Response(
                    {
                        "message": f'Terminated {result["terminated_count"]} sessions',
                        "result": result,
                    }
                )
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class TerminateAllSessionsView(APIView):
    """View for terminating all sessions except current"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        description="Terminate all sessions except the current one.",
    )
    @transaction.atomic
    def post(self, request):
        try:
            LoginSessionService.deactivate_all_user_sessions(request.user)

            from ..services.user_activity import UserActivityService

            UserActivityService.log_activity(
                user=request.user,
                action="logout_all_devices",
                description="User terminated all sessions on other devices",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )

            return Response({"message": "All other sessions terminated successfully"})

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class Check2FAStatusView(APIView):
    """View for checking 2FA status"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "two_factor_enabled": {"type": "boolean"},
                },
            }
        },
        description="Check whether two-factor authentication is enabled for the current user.",
    )
    def get(self, request):
        try:
            is_enabled = UserSecuritySettingsService.is_2fa_enabled(request.user)
            return Response(
                {"user_id": request.user.id, "two_factor_enabled": is_enabled}
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
