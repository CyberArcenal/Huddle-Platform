from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import UsersPagination
from django.db import transaction
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
from rest_framework import serializers
from ..serializers.admin import AdminUserListSerializer


# ----- New input serializer for AdminCleanupView -----
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


# ------------------------------------------------------


class PaginatedAdminUserListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = AdminUserListSerializer(many=True)


class AdminUserListView(APIView):
    """Admin view for listing users with filters"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
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
        responses={200: PaginatedAdminUserListSerializer},
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
            serializer = AdminUserListSerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminUserDetailView(APIView):
    """Admin view for user details"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        responses={
            200: {
                "type": "object",
                "properties": {
                    "user": AdminUserListSerializer().data,
                    "recent_activities": {"type": "array"},
                    "recent_security_logs": {"type": "array"},
                },
            }
        },
        description="Retrieve detailed user information including recent activities and security logs.",
    )
    def get(self, request, user_id):
        try:
            user = get_object_or_404(User, id=user_id)

            serializer = AdminUserListSerializer(user, context={"request": request})

            recent_activities = UserActivity.objects.filter(user=user).order_by(
                "-timestamp"
            )[:10]

            security_logs = SecurityLog.objects.filter(user=user).order_by(
                "-created_at"
            )[:10]

            from ..serializers.activity import UserActivitySerializer
            from ..serializers.security import SecurityLogSerializer

            activity_serializer = UserActivitySerializer(
                recent_activities, many=True, context={"request": request}
            )

            security_serializer = SecurityLogSerializer(
                security_logs, many=True, context={"request": request}
            )

            return Response(
                {
                    "user": serializer.data,
                    "recent_activities": activity_serializer.data,
                    "recent_security_logs": security_serializer.data,
                }
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=AdminUserUpdateSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "user": AdminUserListSerializer().data,
                },
            }
        },
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

                return Response(
                    {
                        "message": "User updated successfully",
                        "user": AdminUserListSerializer(
                            updated_user, context={"request": request}
                        ).data,
                    }
                )

            return Response(
                {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminCreateUserView(APIView):
    """Admin view for creating users"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        request=AdminUserCreateSerializer,
        responses={201: AdminUserListSerializer},
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

                return Response(
                    {
                        "message": "User created successfully",
                        "user": AdminUserListSerializer(
                            user, context={"request": request}
                        ).data,
                    },
                    status=status.HTTP_201_CREATED,
                )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class AdminBulkUserActionView(APIView):
    """Admin view for bulk user actions"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        request=BulkUserActionSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "results": {"type": "object"},
                },
            }
        },
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
                        "message": f'Bulk action completed: {results["success"]} successful, {results["failed"]} failed',
                        "results": results,
                    }
                )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class AdminDashboardView(APIView):
    """Admin dashboard with statistics"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        responses={200: {"type": "object"}},
        description="Get admin dashboard statistics: user counts, activity, security events.",
    )
    def get(self, request):
        try:
            total_users = User.objects.count()
            active_users = User.objects.filter(status=UserStatus.ACTIVE).count()
            new_users_today = User.objects.filter(
                created_at__gte=timezone.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            ).count()
            new_users_week = User.objects.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count()

            status_breakdown = (
                User.objects.values("status")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            total_activities = UserActivity.objects.count()
            activities_today = UserActivity.objects.filter(
                timestamp__gte=timezone.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            ).count()

            failed_logins_24h = SecurityLog.objects.filter(
                event_type="failed_login",
                created_at__gte=timezone.now() - timedelta(hours=24),
            ).count()

            password_changes_24h = SecurityLog.objects.filter(
                event_type="password_change",
                created_at__gte=timezone.now() - timedelta(hours=24),
            ).count()

            return Response(
                {
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
                    "timestamp": timezone.now(),
                }
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserExportView(APIView):
    """View for exporting user data (GDPR compliance)"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        responses={200: {"type": "object"}},
        description="Export all data for a user (GDPR compliance).",
    )
    def get(self, request, user_id):
        try:
            user = get_object_or_404(User, id=user_id)

            serializer = UserExportSerializer(user, context={"request": request})

            return Response(
                {
                    "user_id": user_id,
                    "export_timestamp": timezone.now(),
                    "data": serializer.data,
                }
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminCleanupView(APIView):
    """Admin view for cleanup operations"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        request=CleanupActionInputSerializer,  # ✅ Now using dedicated serializer
        responses={200: {"type": "object"}},
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
        serializer = CleanupActionInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        action = data["action"]

        try:
            from ..services.login_session import LoginSessionService
            from ..services.blacklisted_access_token import (
                BlacklistedAccessTokenService,
            )
            from ..services.otp_request import OtpRequestService
            from ..services.login_checkpoint import LoginCheckpointService

            if action == "cleanup_expired_sessions":
                count = LoginSessionService.cleanup_expired_sessions()
                return Response(
                    {"message": f"Cleaned up {count} expired sessions", "count": count}
                )

            elif action == "cleanup_expired_tokens":
                count = BlacklistedAccessTokenService.cleanup_expired_tokens()
                return Response(
                    {
                        "message": f"Cleaned up {count} expired blacklisted tokens",
                        "count": count,
                    }
                )

            elif action == "cleanup_expired_otps":
                count = OtpRequestService.cleanup_expired_otps()
                return Response(
                    {"message": f"Cleaned up {count} expired OTPs", "count": count}
                )

            elif action == "cleanup_expired_checkpoints":
                count = LoginCheckpointService.cleanup_expired_checkpoints()
                return Response(
                    {
                        "message": f"Cleaned up {count} expired checkpoints",
                        "count": count,
                    }
                )

            elif action == "cleanup_old_logs":
                days = data.get("days", 90)
                count = SecurityLogService.cleanup_old_logs(days)
                return Response(
                    {
                        "message": f"Cleaned up {count} logs older than {days} days",
                        "count": count,
                    }
                )

            elif action == "cleanup_old_activities":
                days = data.get("days", 365)
                count = UserActivityService.cleanup_old_activities(days)
                return Response(
                    {
                        "message": f"Cleaned up {count} activities older than {days} days",
                        "count": count,
                    }
                )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
