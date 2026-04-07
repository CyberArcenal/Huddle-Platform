# accounts/views/password_reset.py
import logging
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from global_utils.pagination import UsersPagination
from global_utils.security import get_client_ip
from users.models import SecurityLog, UserSecuritySettings
from users.serializers.auth import (
    PasswordChangeRequestSerializer,
    PasswordChangeResponseSerializer,
    PasswordStrengthCheckRequestSerializer,
    PasswordStrengthCheckResponseSerializer,
    PasswordHistoryResponseSerializer,
)
from users.services.user_activity import UserActivityService
from rest_framework import serializers

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers (for drf-spectacular)
# ----------------------------------------------------------------------

class PasswordChangeResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()


class PasswordChangeResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PasswordChangeResponseData()


class PasswordStrengthCheckResponseData(serializers.Serializer):
    strength_score = serializers.IntegerField()
    strength_level = serializers.CharField()
    is_acceptable = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    suggestions = serializers.ListField(child=serializers.CharField())


class PasswordStrengthCheckResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PasswordStrengthCheckResponseData()


class PasswordHistoryEventData(serializers.Serializer):
    event_type = serializers.CharField()
    created_at = serializers.DateTimeField()
    ip_address = serializers.CharField(allow_null=True)
    user_agent = serializers.CharField(allow_null=True)
    success = serializers.BooleanField()


class PasswordHistoryResponseData(serializers.Serializer):
    total_events = serializers.IntegerField()
    events = PasswordHistoryEventData(many=True)


class PasswordHistoryResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PasswordHistoryResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class PasswordChangeView(APIView):
    """
    Change password for authenticated users
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Password Reset"],
        request=PasswordChangeRequestSerializer,
        responses={200: PasswordChangeResponseSerializer},
        examples=[
            OpenApiExample(
                "Password change request",
                value={
                    "current_password": "OldPass123!",
                    "new_password": "NewPass123!",
                    "confirm_password": "NewPass123!",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "status": True,
                    "message": "Password changed successfully",
                    "data": {"user_id": 1},
                },
                response_only=True,
            ),
        ],
        description="Change the authenticated user's password.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = PasswordChangeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        user = request.user

        current_password = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]
        confirm_password = serializer.validated_data["confirm_password"]

        # Check if passwords match
        if new_password != confirm_password:
            return Response(
                {
                    "status": False,
                    "message": "New passwords do not match",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if new password is different from current
        if current_password == new_password:
            return Response(
                {
                    "status": False,
                    "message": "New password must be different from current password",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify current password
        if not check_password(current_password, user.password):
            # Log failed attempt
            SecurityLog.objects.create(
                user=user,
                event_type="password_change_failed",
                ip_address=client_ip,
                user_agent=user_agent,
                details="Incorrect current password provided",
            )
            return Response(
                {
                    "status": False,
                    "message": "Current password is incorrect",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate password strength
        password_errors = self._validate_password_strength(new_password)
        if password_errors:
            return Response(
                {
                    "status": False,
                    "message": "Password does not meet requirements",
                    "data": {"errors": password_errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Update password
            user.password = make_password(new_password)
            user.save()

            # Log successful change
            SecurityLog.objects.create(
                user=user,
                event_type="password_changed",
                ip_address=client_ip,
                user_agent=user_agent,
                details="Password changed successfully",
            )

            # Log activity
            UserActivityService.log_activity(
                user=user,
                action="password_change",
                description="User changed password",
                ip_address=client_ip,
                user_agent=user_agent,
            )

            # Optionally invalidate other sessions (except current)
            self._invalidate_other_sessions(user, request.session.session_key)

            return Response(
                {
                    "status": True,
                    "message": "Password changed successfully",
                    "data": {"user_id": user.id},
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception(f"Password change failed for user {user.id}: {e}")
            return Response(
                {
                    "status": False,
                    "message": "An error occurred while changing password",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _validate_password_strength(self, password):
        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not any(char.isdigit() for char in password):
            errors.append("Password must contain at least one number")
        if not any(char.isupper() for char in password):
            errors.append("Password must contain at least one uppercase letter")
        if not any(char.islower() for char in password):
            errors.append("Password must contain at least one lowercase letter")
        if not any(char in "!@#$%^&*()_+-=[]{}|;:,.<>?`~" for char in password):
            errors.append("Password must contain at least one special character")
        common_passwords = ["password", "12345678", "qwerty", "admin", "letmein"]
        if password.lower() in common_passwords:
            errors.append("Password is too common")
        return errors

    def _invalidate_other_sessions(self, user, current_session_key):
        try:
            from django.contrib.sessions.models import Session
            from django.contrib.auth import SESSION_KEY
            sessions = Session.objects.filter(expire_date__gte=timezone.now()).exclude(
                session_key=current_session_key
            )
            for session in sessions:
                session_data = session.get_decoded()
                if session_data.get(SESSION_KEY) == str(user.id):
                    session.delete()
        except Exception as e:
            logger.warning(f"Could not invalidate other sessions: {e}")


class PasswordStrengthCheckView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Password Reset"],
        request=PasswordStrengthCheckRequestSerializer,
        responses={200: PasswordStrengthCheckResponseSerializer},
        description="Check password strength without changing it.",
    )
    def post(self, request):
        serializer = PasswordStrengthCheckRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        password = serializer.validated_data["password"]
        errors = self._validate_password_strength(password)
        score = self._calculate_password_strength(password)

        return Response(
            {
                "status": True,
                "message": "Password strength checked.",
                "data": {
                    "strength_score": score,
                    "strength_level": self._get_strength_level(score),
                    "is_acceptable": len(errors) == 0,
                    "errors": errors,
                    "suggestions": self._get_password_suggestions(password),
                },
            },
            status=status.HTTP_200_OK,
        )

    # ... (same helper methods as before, but you can keep them private)
    def _validate_password_strength(self, password): ...
    def _calculate_password_strength(self, password): ...
    def _get_strength_level(self, score): ...
    def _get_password_suggestions(self, password): ...


class PasswordHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = UsersPagination

    @extend_schema(
        tags=["Password Reset"],
        parameters=[
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: PasswordHistoryResponseSerializer},
        description="Get password change history (successful and failed).",
    )
    def get(self, request):
        try:
            user = request.user
            events = SecurityLog.objects.filter(
                user=user,
                event_type__in=["password_changed", "password_change_failed"]
            ).order_by("-created_at")

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(events, request)

            events_data = [
                {
                    "event_type": e.event_type,
                    "created_at": e.created_at,
                    "ip_address": e.ip_address,
                    "user_agent": e.user_agent,
                    "success": e.event_type == "password_changed",
                }
                for e in page
            ]

            return Response(
                {
                    "status": True,
                    "message": "Password history retrieved.",
                    "data": {
                        "total_events": paginator.page.paginator.count,
                        "events": events_data,
                    },
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("PasswordHistoryView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )