import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import inline_serializer
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from global_utils.pagination import UsersPagination
from users.serializers.session import (
    BulkTerminateSessionsSerializer,
    LoginSessionSerializer,
    TerminateSessionSerializer,
)

from ..services.security_log import SecurityLogService
from ..services.user_security_settings import UserSecuritySettingsService
from ..services.login_session import LoginSessionService
from ..services.blacklisted_access_token import BlacklistedAccessTokenService
from ..serializers.security import (
    BulkTerminateSessionsResponseSerializer,
    ChangePasswordSerializer,
    Check2FAStatusResponseSerializer,
    Disable2FAResponseSerializer,
    Enable2FAResponseSerializer,
    EnableTwoFactorSerializer,
    DisableTwoFactorSerializer,
    FailedLoginAttemptsResponseSerializer,
    SecuritySettingsGetResponseSerializer,
    SecuritySettingsUpdateResponseSerializer,
    SuspiciousActivitiesResponseSerializer,
    TerminateAllSessionsResponseSerializer,
    TerminateSessionResponseSerializer,
    UpdateSecuritySettingsSerializer,
    SecurityLogSerializer,
)
from django.db import transaction
from ..models import UserSecuritySettings, SecurityLog, LoginSession
from ..services.user_activity import UserActivityService

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_security_logs(paginator, page, request):
    """
    Construct a paginated data dict for SecurityLogSerializer.
    """
    serializer = SecurityLogSerializer(page, many=True, context={"request": request})
    data = {
        "page": paginator.page.number,
        "hasNext": paginator.page.has_next(),
        "hasPrev": paginator.page.has_previous(),
        "count": paginator.page.paginator.count,
        "next": paginator.get_next_link(),
        "previous": paginator.get_previous_link(),
        "results": serializer.data,
    }
    return data


def wrap_paginated_sessions(paginator, page, request):
    """
    Construct a paginated data dict for LoginSessionSerializer.
    """
    serializer = LoginSessionSerializer(page, many=True, context={"request": request})
    data = {
        "page": paginator.page.number,
        "hasNext": paginator.page.has_next(),
        "hasPrev": paginator.page.has_previous(),
        "count": paginator.page.paginator.count,
        "next": paginator.get_next_link(),
        "previous": paginator.get_previous_link(),
        "results": serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------


class PaginatedSecurityLogData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = SecurityLogSerializer(many=True)


class PaginatedSecurityLogResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedSecurityLogData()


class Enable2FAResponseData(serializers.Serializer):
    two_factor_enabled = serializers.BooleanField()
    user_id = serializers.IntegerField()


class Enable2FAResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = Enable2FAResponseData()


class Disable2FAResponseData(serializers.Serializer):
    two_factor_enabled = serializers.BooleanField()
    user_id = serializers.IntegerField()


class Disable2FAResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = Disable2FAResponseData()


class SecuritySettingsGetResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()
    settings = UpdateSecuritySettingsSerializer()


class SecuritySettingsGetResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SecuritySettingsGetResponseData()


class SecuritySettingsUpdateResponseData(serializers.Serializer):
    settings = UpdateSecuritySettingsSerializer()


class SecuritySettingsUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SecuritySettingsUpdateResponseData()


class FailedLoginAttemptsResponseData(serializers.Serializer):
    count = serializers.IntegerField()
    hours = serializers.IntegerField()
    attempts = SecurityLogSerializer(many=True)


class FailedLoginAttemptsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = FailedLoginAttemptsResponseData()


class SuspiciousActivitiesResponseData(serializers.Serializer):
    count = serializers.IntegerField()
    activities = SecurityLogSerializer(many=True)


class SuspiciousActivitiesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SuspiciousActivitiesResponseData()


class PaginatedLoginSessionData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = LoginSessionSerializer(many=True)


class PaginatedLoginSessionResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedLoginSessionData()


class TerminateSessionResponseData(serializers.Serializer):
    message = serializers.CharField()


class TerminateSessionResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TerminateSessionResponseData()


class BulkTerminateSessionsResponseData(serializers.Serializer):
    message = serializers.CharField()
    result = serializers.DictField()


class BulkTerminateSessionsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = BulkTerminateSessionsResponseData()


class TerminateAllSessionsResponseData(serializers.Serializer):
    message = serializers.CharField()


class TerminateAllSessionsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TerminateAllSessionsResponseData()


class Check2FAStatusResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()
    two_factor_enabled = serializers.BooleanField()


class Check2FAStatusResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = Check2FAStatusResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------


class Enable2FAView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
        request=EnableTwoFactorSerializer,
        responses={200: Enable2FAResponseSerializer},
        examples=[
            OpenApiExample(
                "Enable 2FA request",
                value={"verification_code": "123456"},
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "status": True,
                    "message": "Two-factor authentication enabled successfully",
                    "data": {"two_factor_enabled": True, "user_id": 1},
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
                        "status": True,
                        "message": "Two-factor authentication enabled successfully",
                        "data": {
                            "two_factor_enabled": settings.two_factor_enabled,
                            "user_id": request.user.id,
                        },
                    }
                )
            except Exception as e:
                logger.exception("Enable2FAView error")
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
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class Disable2FAView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
        request=DisableTwoFactorSerializer,
        responses={200: Disable2FAResponseSerializer},
        examples=[
            OpenApiExample(
                "Disable 2FA request",
                value={"verification_code": "123456"},
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "status": True,
                    "message": "Two-factor authentication disabled successfully",
                    "data": {"two_factor_enabled": False, "user_id": 1},
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
                        "status": True,
                        "message": "Two-factor authentication disabled successfully",
                        "data": {
                            "two_factor_enabled": settings.two_factor_enabled,
                            "user_id": request.user.id,
                        },
                    }
                )
            except Exception as e:
                logger.exception("Disable2FAView error")
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
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class SecuritySettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
        responses={200: SecuritySettingsGetResponseSerializer},
        description="Get the current user's security settings.",
    )
    def get(self, request):
        try:
            settings = UserSecuritySettingsService.get_or_create_settings(request.user)
            serializer = UpdateSecuritySettingsSerializer(settings)
            return Response(
                {
                    "status": True,
                    "message": "Security settings retrieved.",
                    "data": {"user_id": request.user.id, "settings": serializer.data},
                }
            )
        except Exception as e:
            logger.exception("SecuritySettingsView GET error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Security"],
        request=UpdateSecuritySettingsSerializer,
        responses={200: SecuritySettingsUpdateResponseSerializer},
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
                output_serializer = UpdateSecuritySettingsSerializer(updated_settings)
                return Response(
                    {
                        "status": True,
                        "message": "Security settings updated successfully",
                        "data": {"settings": output_serializer.data},
                    }
                )
            except Exception as e:
                logger.exception("SecuritySettingsView PUT error")
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
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class SecurityLogsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
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
        responses={200: PaginatedSecurityLogResponseSerializer},
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
            paginated_data = wrap_paginated_security_logs(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Security logs retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("SecurityLogsView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FailedLoginAttemptsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
        responses={200: FailedLoginAttemptsResponseSerializer},
        examples=[
            OpenApiExample(
                "Response",
                value={
                    "status": True,
                    "message": "Failed login attempts retrieved.",
                    "data": {
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
                },
                response_only=True,
            )
        ],
        description="Get failed login attempts for the current user.",
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
                {
                    "status": True,
                    "message": "Failed login attempts retrieved.",
                    "data": {
                        "count": count,
                        "hours": hours,
                        "attempts": serializer.data,
                    },
                }
            )
        except Exception as e:
            logger.exception("FailedLoginAttemptsView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SuspiciousActivitiesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Maximum number of activities",
                required=False,
            ),
        ],
        responses={200: SuspiciousActivitiesResponseSerializer},
        description="Get suspicious activities flagged for the current user.",
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 20))
            activities = SecurityLogService.get_suspicious_activities(
                user=request.user, limit=limit
            )
            serializer = SecurityLogSerializer(activities, many=True)

            return Response(
                {
                    "status": True,
                    "message": "Suspicious activities retrieved.",
                    "data": {
                        "count": len(activities),
                        "activities": serializer.data,
                    },
                }
            )
        except Exception as e:
            logger.exception("SuspiciousActivitiesView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ActiveSessionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
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
        responses={200: PaginatedLoginSessionResponseSerializer},
        description="Get all active login sessions for the current user.",
    )
    def get(self, request):
        try:
            sessions = LoginSessionService.get_active_user_sessions(request.user)
            paginator = UsersPagination()
            page = paginator.paginate_queryset(sessions, request)
            paginated_data = wrap_paginated_sessions(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Active sessions retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("ActiveSessionsView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TerminateSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
        request=TerminateSessionSerializer,
        responses={200: TerminateSessionResponseSerializer},
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
                    return Response(
                        {
                            "status": True,
                            "message": "Session terminated successfully",
                            "data": {"message": "Session terminated successfully"},
                        }
                    )
                else:
                    return Response(
                        {
                            "status": False,
                            "message": "Failed to terminate session",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception as e:
                logger.exception("TerminateSessionView error")
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
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class BulkTerminateSessionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
        request=BulkTerminateSessionsSerializer,
        responses={200: BulkTerminateSessionsResponseSerializer},
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
                        "status": True,
                        "message": f'Terminated {result["terminated_count"]} sessions',
                        "data": {
                            "message": f'Terminated {result["terminated_count"]} sessions',
                            "result": result,
                        },
                    }
                )
            except Exception as e:
                logger.exception("BulkTerminateSessionsView error")
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
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class TerminateAllSessionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
        responses={200: TerminateAllSessionsResponseSerializer},
        description="Terminate all sessions except the current one.",
    )
    @transaction.atomic
    def post(self, request):
        try:
            LoginSessionService.deactivate_all_user_sessions(request.user)

            UserActivityService.log_activity(
                user=request.user,
                action="logout_all_devices",
                description="User terminated all sessions on other devices",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )

            return Response(
                {
                    "status": True,
                    "message": "All other sessions terminated successfully",
                    "data": {"message": "All other sessions terminated successfully"},
                }
            )
        except Exception as e:
            logger.exception("TerminateAllSessionsView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class Check2FAStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Security"],
        responses={200: Check2FAStatusResponseSerializer},
        description="Check whether two-factor authentication is enabled for the current user.",
    )
    def get(self, request):
        try:
            is_enabled = UserSecuritySettingsService.is_2fa_enabled(request.user)
            return Response(
                {
                    "status": True,
                    "message": "2FA status retrieved.",
                    "data": {
                        "user_id": request.user.id,
                        "two_factor_enabled": is_enabled,
                    },
                }
            )
        except Exception as e:
            logger.exception("Check2FAStatusView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
