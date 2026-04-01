from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from django.db import transaction

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import UsersPagination
from ..serializers.admin import (
    AdminUserUpdateSerializer,
    AdminUserCreateSerializer,
    AdminUserListSerializer,
    BulkUserActionSerializer,
    UserExportSerializer,
)
from ..services.user import UserService
from ..services.security_log import SecurityLogService
from ..services.user_activity import UserActivityService
from ..models import User, UserStatus, SecurityLog, UserActivity
from ..serializers.activity import UserActivitySerializer
from ..serializers.security import SecurityLogSerializer

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Input serializers
# ----------------------------------------------------------------------
class CleanupActionInputSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=[
            "cleanup_expired_sessions",
            "cleanup_expired_tokens",
            "cleanup_expired_otps",
            "cleanup_expired_checkpoints",
            "cleanup_old_logs",
            "cleanup_old_activities",
        ],
        help_text="Cleanup action to perform",
    )
    days = serializers.IntegerField(
        required=False,
        min_value=1,
        help_text="Number of days (used for old logs/activities)",
    )


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_admin_users(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedAdminUserData.
    """
    serializer = AdminUserListSerializer(page, many=True, context={'request': request})
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

class PaginatedAdminUserData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = AdminUserListSerializer(many=True)


class AdminUserListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedAdminUserData()


class AdminUserDetailResponseData(serializers.Serializer):
    user = AdminUserListSerializer()
    recent_activities = UserActivitySerializer(many=True)
    recent_security_logs = SecurityLogSerializer(many=True)


class AdminUserDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = AdminUserDetailResponseData()


class AdminUserUpdateResponseData(serializers.Serializer):
    user = AdminUserListSerializer()


class AdminUserUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = AdminUserUpdateResponseData()


class AdminCreateUserResponseData(serializers.Serializer):
    user = AdminUserListSerializer()


class AdminCreateUserResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = AdminCreateUserResponseData()


class AdminBulkUserActionResponseData(serializers.Serializer):
    success = serializers.IntegerField()
    failed = serializers.IntegerField()


class AdminBulkUserActionResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = AdminBulkUserActionResponseData()


class AdminDashboardData(serializers.Serializer):
    user_statistics = serializers.DictField()
    activity_statistics = serializers.DictField()
    security_statistics = serializers.DictField()
    timestamp = serializers.DateTimeField()


class AdminDashboardResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = AdminDashboardData()


class UserExportResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()
    export_timestamp = serializers.DateTimeField()
    data = serializers.DictField()


class UserExportResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserExportResponseData()


class CleanupActionResponseData(serializers.Serializer):
    count = serializers.IntegerField()


class CleanupActionResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = CleanupActionResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class AdminUserListView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                description="Filter by user status",
                required=False,
            ),
            OpenApiParameter(
                name="is_verified",
                type=bool,
                description="Filter by verification status",
                required=False,
            ),
            OpenApiParameter(
                name="is_active",
                type=bool,
                description="Filter by active status",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=str,
                description="Search in username, email, name",
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
        responses={200: AdminUserListResponseSerializer},
        description="List users with admin filters and pagination.",
    )
    def get(self, request):
        try:
            status_filter = request.query_params.get("status")
            is_verified = request.query_params.get("is_verified")
            is_active = request.query_params.get("is_active")
            search = request.query_params.get("search", "").strip()

            queryset = User.objects.all()

            if status_filter:
                queryset = queryset.filter(status=status_filter)
            if is_verified is not None:
                queryset = queryset.filter(is_verified=is_verified.lower() == "true")
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == "true")
            if search:
                queryset = queryset.filter(
                    Q(username__icontains=search)
                    | Q(email__icontains=search)
                    | Q(first_name__icontains=search)
                    | Q(last_name__icontains=search)
                )

            queryset = queryset.order_by("-date_joined")

            paginator = UsersPagination()
            page = paginator.paginate_queryset(queryset, request)
            paginated_data = wrap_paginated_admin_users(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Admin users list retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("AdminUserListView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AdminUserDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        responses={200: AdminUserDetailResponseSerializer},
        description="Retrieve detailed user information including recent activities and security logs.",
    )
    def get(self, request, user_id):
        try:
            user = get_object_or_404(User, id=user_id)

            user_serializer = AdminUserListSerializer(user, context={"request": request})
            recent_activities = UserActivity.objects.filter(user=user).order_by("-timestamp")[:10]
            security_logs = SecurityLog.objects.filter(user=user).order_by("-created_at")[:10]

            activity_serializer = UserActivitySerializer(
                recent_activities, many=True, context={"request": request}
            )
            security_serializer = SecurityLogSerializer(
                security_logs, many=True, context={"request": request}
            )

            return Response(
                {
                    "status": True,
                    "message": "User details retrieved.",
                    "data": {
                        "user": user_serializer.data,
                        "recent_activities": activity_serializer.data,
                        "recent_security_logs": security_serializer.data,
                    },
                }
            )
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception("AdminUserDetailView error for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Admin"],
        request=AdminUserUpdateSerializer,
        responses={200: AdminUserUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update user",
                value={"status": "suspended", "is_verified": True},
                request_only=True,
            )
        ],
        description="Update a user's details as admin.",
    )
    @transaction.atomic
    def put(self, request, user_id):
        try:
            user = get_object_or_404(User, id=user_id)
            serializer = AdminUserUpdateSerializer(
                user, data=request.data, partial=True, context={"request": request}
            )
            if serializer.is_valid():
                updated_user = serializer.save()
                user_serializer = AdminUserListSerializer(updated_user, context={"request": request})
                return Response(
                    {
                        "status": True,
                        "message": "User updated successfully",
                        "data": {"user": user_serializer.data},
                    }
                )
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception("AdminUserDetailView PUT error for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AdminCreateUserView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        request=AdminUserCreateSerializer,
        responses={201: AdminCreateUserResponseSerializer},
        examples=[
            OpenApiExample(
                "Create user",
                value={
                    "username": "newuser",
                    "email": "user@example.com",
                    "password": "securepass123",
                    "first_name": "John",
                    "last_name": "Doe",
                    "status": "active",
                    "is_verified": True,
                    "is_staff": False,
                },
                request_only=True,
            )
        ],
        description="Create a new user as admin.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = AdminUserCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            try:
                user = serializer.save()
                user_serializer = AdminUserListSerializer(user, context={"request": request})
                return Response(
                    {
                        "status": True,
                        "message": "User created successfully",
                        "data": {"user": user_serializer.data},
                    },
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                logger.exception("AdminCreateUserView error")
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


class AdminBulkUserActionView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        request=BulkUserActionSerializer,
        responses={200: AdminBulkUserActionResponseSerializer},
        examples=[
            OpenApiExample(
                "Bulk action",
                value={"action": "deactivate", "user_ids": [1, 2, 3]},
                request_only=True,
            )
        ],
        description="Perform a bulk action (e.g., deactivate, activate) on multiple users.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = BulkUserActionSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            try:
                results = serializer.execute()
                return Response(
                    {
                        "status": True,
                        "message": f'Bulk action completed: {results["success"]} successful, {results["failed"]} failed',
                        "data": {"success": results["success"], "failed": results["failed"]},
                    }
                )
            except Exception as e:
                logger.exception("AdminBulkUserActionView error")
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


class AdminDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        responses={200: AdminDashboardResponseSerializer},
        description="Get admin dashboard statistics: user counts, activity, security events.",
    )
    def get(self, request):
        try:
            now = timezone.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            total_users = User.objects.count()
            active_users = User.objects.filter(status=UserStatus.ACTIVE).count()
            new_users_today = User.objects.filter(created_at__gte=today_start).count()
            new_users_week = User.objects.filter(created_at__gte=now - timedelta(days=7)).count()

            status_breakdown = (
                User.objects.values("status")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            total_activities = UserActivity.objects.count()
            activities_today = UserActivity.objects.filter(timestamp__gte=today_start).count()

            failed_logins_24h = SecurityLog.objects.filter(
                event_type="failed_login",
                created_at__gte=now - timedelta(hours=24),
            ).count()

            password_changes_24h = SecurityLog.objects.filter(
                event_type="password_change",
                created_at__gte=now - timedelta(hours=24),
            ).count()

            data = {
                "user_statistics": {
                    "total_users": total_users,
                    "active_users": active_users,
                    "new_users_today": new_users_today,
                    "new_users_week": new_users_week,
                    "status_breakdown": list(status_breakdown),
                },
                "activity_statistics": {
                    "total_activities": total_activities,
                    "activities_today": activities_today,
                },
                "security_statistics": {
                    "failed_logins_24h": failed_logins_24h,
                    "password_changes_24h": password_changes_24h,
                },
                "timestamp": now,
            }

            return Response(
                {
                    "status": True,
                    "message": "Dashboard statistics retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("AdminDashboardView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserExportView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        responses={200: UserExportResponseSerializer},
        description="Export all data for a user (GDPR compliance).",
    )
    def get(self, request, user_id):
        try:
            user = get_object_or_404(User, id=user_id)
            export_serializer = UserExportSerializer(user, context={"request": request})
            data = {
                "user_id": user_id,
                "export_timestamp": timezone.now(),
                "data": export_serializer.data,
            }
            return Response(
                {
                    "status": True,
                    "message": "User data exported successfully.",
                    "data": data,
                }
            )
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception("UserExportView error for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AdminCleanupView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        request=CleanupActionInputSerializer,
        responses={200: CleanupActionResponseSerializer},
        examples=[
            OpenApiExample(
                "Cleanup expired sessions",
                value={"action": "cleanup_expired_sessions"},
                request_only=True,
            ),
            OpenApiExample(
                "Cleanup old logs",
                value={"action": "cleanup_old_logs", "days": 90},
                request_only=True,
            ),
        ],
        description="Perform cleanup operations (expired sessions, tokens, logs, etc.).",
    )
    @transaction.atomic
    def post(self, request):
        input_serializer = CleanupActionInputSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": input_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = input_serializer.validated_data
        action = data["action"]

        try:
            from ..services.login_session import LoginSessionService
            from ..services.blacklisted_access_token import BlacklistedAccessTokenService
            from ..services.otp_request import OtpRequestService
            from ..services.login_checkpoint import LoginCheckpointService

            if action == "cleanup_expired_sessions":
                count = LoginSessionService.cleanup_expired_sessions()
                message = f"Cleaned up {count} expired sessions"
            elif action == "cleanup_expired_tokens":
                count = BlacklistedAccessTokenService.cleanup_expired_tokens()
                message = f"Cleaned up {count} expired blacklisted tokens"
            elif action == "cleanup_expired_otps":
                count = OtpRequestService.cleanup_expired_otps()
                message = f"Cleaned up {count} expired OTPs"
            elif action == "cleanup_expired_checkpoints":
                count = LoginCheckpointService.cleanup_expired_checkpoints()
                message = f"Cleaned up {count} expired checkpoints"
            elif action == "cleanup_old_logs":
                days = data.get("days", 90)
                count = SecurityLogService.cleanup_old_logs(days)
                message = f"Cleaned up {count} logs older than {days} days"
            elif action == "cleanup_old_activities":
                days = data.get("days", 365)
                count = UserActivityService.cleanup_old_activities(days)
                message = f"Cleaned up {count} activities older than {days} days"
            else:
                return Response(
                    {
                        "status": False,
                        "message": f"Unknown action: {action}",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {
                    "status": True,
                    "message": message,
                    "data": {"count": count},
                }
            )
        except Exception as e:
            logger.exception("AdminCleanupView error for action %s", action)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )