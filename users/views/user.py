from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from core import settings
from core.settings.dev import LOGGER
from global_utils.pagination import UsersPagination
from users.models.user_activity import UserActivity
from users.serializers.user.minimal import UserMinimalSerializer
from users.serializers.user.profile import UserProfileSerializer

from ..services.user import UserService
from ..services.security_log import SecurityLogService
from ..services.login_session import LoginSessionService
from ..serializers.user.base import (
    UserCreateSerializer,
    UserProfileSchemaUpdateSerializer,
    UserRegisterSerializer,
    UserUpdateSerializer,
    UserStatusSerializer,
)
from ..models import User, UserStatus

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_users(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedUserListData.
    """
    serializer = UserMinimalSerializer(page, many=True, context={'request': request})
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

class PaginatedUserListData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserMinimalSerializer(many=True)


class UserRegisterResponseData(serializers.Serializer):
    message = serializers.CharField()
    user_id = serializers.IntegerField()


class UserRegisterResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserRegisterResponseData(allow_null=True)


class UserProfileResponseData(serializers.Serializer):
    user = UserProfileSerializer()


class UserProfileResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserProfileResponseData()


class UserUpdateResponseData(serializers.Serializer):
    user = UserProfileSerializer()


class UserUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserUpdateResponseData()

class UserSearchResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedUserListData()


class UserStatusUpdateResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()
    status = serializers.CharField()


class UserStatusUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserStatusUpdateResponseData()


class UserDeactivateResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()
    status = serializers.CharField()


class UserDeactivateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserDeactivateResponseData()


class VerifyUserResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()
    is_verified = serializers.BooleanField()


class VerifyUserResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = VerifyUserResponseData()


class CheckUsernameResponseData(serializers.Serializer):
    available = serializers.BooleanField()
    username = serializers.CharField()
    message = serializers.CharField()


class CheckUsernameResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = CheckUsernameResponseData()


class CheckEmailResponseData(serializers.Serializer):
    available = serializers.BooleanField()
    email = serializers.CharField()
    message = serializers.CharField()


class CheckEmailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = CheckEmailResponseData()


class ResendVerificationResponseData(serializers.Serializer):
    message = serializers.CharField()


class ResendVerificationResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ResendVerificationResponseData(allow_null=True)


class EmailVerificationResponseData(serializers.Serializer):
    message = serializers.CharField()


class EmailVerificationResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EmailVerificationResponseData()


# ----------------------------------------------------------------------
# Input serializers
# ----------------------------------------------------------------------
class UserDeactivateInputSerializer(serializers.Serializer):
    password = serializers.CharField(
        write_only=True, help_text="Current password for confirmation"
    )
    confirm = serializers.BooleanField(help_text="Must be true to confirm deactivation")


class ResendSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    user_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs.get('email') and not attrs.get('user_id'):
            raise serializers.ValidationError("Either email or user_id is required")
        return attrs


class VerifyEmailSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True)
    otp_code = serializers.CharField(max_length=6, min_length=6, required=True)


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

import redis
from rest_framework.permissions import IsAuthenticated
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

class UserOnlineStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id=None):
        if user_id:
            # Check single user
            is_online = redis_client.exists(f"online:{user_id}")
            return Response({"user_id": user_id, "online": bool(is_online)})
        else:
            # Bulk check: get all online users from a set
            # You can maintain a set of online users, or just iterate over IDs
            user_ids = request.query_params.getlist('ids')
            statuses = {}
            for uid in user_ids:
                statuses[uid] = redis_client.exists(f"online:{uid}")
            return Response(statuses)
        
        
class UserRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["User's"],
        request=UserRegisterSerializer,
        responses={201: UserRegisterResponseSerializer, 200: UserRegisterResponseSerializer},
        description="Register a new user or resend verification for inactive accounts.",
    )
    @transaction.atomic
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        existing_user = UserService.get_user_by_email(email)

        # Handle existing inactive user (resend OTP)
        if existing_user and not existing_user.is_active:
            try:
                from users.services.otp_request import OtpRequestService
                from notifications.services.notification_queue import NotificationQueueService

                otp_request = OtpRequestService.create_otp_request(
                    user=existing_user,
                    email=email,
                    expires_in_minutes=10,
                    otp_type="email"
                )
                NotificationQueueService.queue_notification(
                    channel="email",
                    recipient=email,
                    subject="Email Verification",
                    message=f"Your verification code is: {otp_request.otp_code}",
                    metadata={"otp_code": otp_request.otp_code, "user_id": existing_user.id}
                )
                return Response(
                    {
                        "status": True,
                        "message": "Account not yet verified. A new verification email has been sent.",
                        "data": {"message": "Verification email sent", "user_id": existing_user.id},
                    },
                    status=status.HTTP_200_OK
                )
            except Exception as e:
                logger.exception("Failed to resend OTP for inactive user")
                return Response(
                    {
                        "status": False,
                        "message": "Failed to send verification email. Please try again later.",
                        "data": None,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # If existing user is active, return error
        if existing_user and existing_user.is_active:
            return Response(
                {
                    "status": False,
                    "message": "Email already registered.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # New user: validate and create
        serializer = UserRegisterSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    from users.services.otp_request import OtpRequestService
                    from notifications.services.notification_queue import NotificationQueueService

                    user = serializer.save()
                    otp_request = OtpRequestService.create_otp_request(
                        user=user,
                        email=user.email,
                        expires_in_minutes=10,
                        otp_type="email"
                    )
                    NotificationQueueService.queue_notification(
                        channel="email",
                        recipient=user.email,
                        subject="Email Verification",
                        message=f"Your verification code is: {otp_request.otp_code}",
                        metadata={"otp_code": otp_request.otp_code, "user_id": user.id}
                    )
                    return Response(
                        {
                            "status": True,
                            "message": "Verification email sent. Please check your inbox.",
                            "data": {"message": "Verification email sent", "user_id": user.id},
                        },
                        status=status.HTTP_201_CREATED,
                    )
            except Exception as e:
                logger.exception("Registration failed for new user")
                return Response(
                    {
                        "status": False,
                        "message": "Registration failed. Please try again later.",
                        "data": None,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            # Validation errors from the serializer
            return Response(
                {
                    "status": False,
                    "message": "Validation failed",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )


class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        responses={200: UserProfileResponseSerializer},
        description="Get the profile of the currently authenticated user.",
    )
    def get(self, request):
        try:
            serializer = UserProfileSerializer(request.user, context={"request": request})
            # logger.debug(f"Retrieved profile for user {request.user.id}: {serializer.data}")
            return Response(
                {
                    "status": True,
                    "message": "Profile retrieved.",
                    "data": {"user": serializer.data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user profile")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User's"],
        request=UserProfileSchemaUpdateSerializer,
        responses={200: UserUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update profile",
                value={"bio": "New bio", "phone_number": "+1234567890"},
                request_only=True,
            )
        ],
        description="Update the profile of the currently authenticated user.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            try:
                user = serializer.save()

                from ..services.user_activity import UserActivityService

                UserActivityService.log_activity(
                    user=request.user,
                    action="update_profile",
                    description="User updated profile information",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )

                data = UserProfileSerializer(user, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Profile updated successfully",
                        "data": {"user": data},
                    }
                )
            except Exception as e:
                logger.exception("Error updating profile")
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


class UserDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        responses={200: UserProfileResponseSerializer},
        description="Retrieve a user's public profile by ID.",
    )
    def get(self, request, user_id):
        try:
            user = UserService.get_user_by_id(user_id)
            if not user or user.status != UserStatus.ACTIVE:
                return Response(
                    {
                        "status": False,
                        "message": "User not found",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = UserProfileSerializer(user, context={"request": request})
            logger.debug(serializer.data)
            return Response(
                {
                    "status": True,
                    "message": "User profile retrieved.",
                    "data": {"user": serializer.data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user detail")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                description="Search query (minimum 2 characters)",
                required=True,
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
        responses={200: UserSearchResponseSerializer},
        description="Search users by username, first name, or last name.",
    )
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query or len(query) < 2:
            return Response(
                {
                    "status": False,
                    "message": "Search query must be at least 2 characters",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            users = UserService.search_users(query)
            paginator = UsersPagination()
            page = paginator.paginate_queryset(users, request)
            paginated_data = wrap_paginated_users(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Search results retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error searching users")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserStatusUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        request=UserStatusSerializer,
        responses={200: UserStatusUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update status",
                value={"user_id": 1, "status": "suspended"},
                request_only=True,
            )
        ],
        description="Update a user's status. Users can update their own status to 'deleted'; admins can set any status.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = UserStatusSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user_id = request.data.get("user_id", request.user.id)
                if user_id != request.user.id and not request.user.is_staff:
                    return Response(
                        {
                            "status": False,
                            "message": "Permission denied",
                            "data": None,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
                if user_id == request.user.id:
                    user = request.user
                else:
                    user = get_object_or_404(User, id=user_id)

                updated_user = serializer.update(user, serializer.validated_data)

                SecurityLogService.create_log(
                    user=updated_user,
                    event_type="status_change",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                    details=f"Status changed to {updated_user.status}",
                )

                return Response(
                    {
                        "status": True,
                        "message": f"User status updated to {updated_user.status}",
                        "data": {
                            "user_id": updated_user.id,
                            "status": updated_user.status,
                        },
                    }
                )
            except Exception as e:
                logger.exception("Error updating user status")
                return Response(
                    {
                        "status": False,
                        "message": "Something went wrong.",
                        "data": None,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        return Response(
            {
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class UserDeactivateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        request=UserDeactivateInputSerializer,
        responses={200: UserDeactivateResponseSerializer},
        examples=[
            OpenApiExample(
                "Deactivate request",
                value={"password": "currentpass", "confirm": True},
                request_only=True,
            )
        ],
        description="Deactivate the current user's account (soft delete). Requires password confirmation.",
    )
    @transaction.atomic
    def post(self, request):
        input_serializer = UserDeactivateInputSerializer(data=request.data)
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
        password = data["password"]
        confirm = data["confirm"]

        if not request.user.check_password(password):
            return Response(
                {
                    "status": False,
                    "message": "Invalid password",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not confirm:
            return Response(
                {
                    "status": False,
                    "message": "Please confirm deactivation",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = UserService.deactivate_user(request.user)
            SecurityLogService.create_log(
                user=user,
                event_type="account_deactivated",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
                details="User deactivated account",
            )
            return Response(
                {
                    "status": True,
                    "message": "Account deactivated successfully",
                    "data": {
                        "user_id": user.id,
                        "status": user.status,
                    },
                }
            )
        except Exception as e:
            logger.exception("Error deactivating user")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        responses={200: VerifyUserResponseSerializer},
        description="Mark the current user's account as verified. (Typically called after email confirmation.)",
    )
    @transaction.atomic
    def post(self, request):
        try:
            user = UserService.verify_user(request.user)

            SecurityLogService.create_log(
                user=user,
                event_type="account_verified",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
                details="User verified account",
            )

            return Response(
                {
                    "status": True,
                    "message": "Account verified successfully",
                    "data": {
                        "user_id": user.id,
                        "is_verified": user.is_verified,
                    },
                }
            )
        except Exception as e:
            logger.exception("Error verifying user")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CheckUsernameView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["User's"],
        parameters=[
            OpenApiParameter(
                name="username",
                type=str,
                description="Username to check",
                required=True,
            ),
        ],
        responses={200: CheckUsernameResponseSerializer},
        examples=[
            OpenApiExample(
                "Username available",
                value={
                    "status": True,
                    "message": "Username is available",
                    "data": {
                        "available": True,
                        "username": "newuser",
                        "message": "Username is available",
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Username taken",
                value={
                    "status": True,
                    "message": "Username is taken",
                    "data": {
                        "available": False,
                        "username": "existing",
                        "message": "Username is taken",
                    },
                },
                response_only=True,
            ),
        ],
        description="Check if a username is available for registration.",
    )
    def get(self, request):
        username = request.query_params.get("username", "").strip().lower()
        if not username:
            return Response(
                {
                    "status": False,
                    "message": "Username is required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(username) < 3:
            return Response(
                {
                    "status": True,
                    "message": "Username must be at least 3 characters",
                    "data": {
                        "available": False,
                        "username": username,
                        "message": "Username must be at least 3 characters",
                    },
                }
            )

        if len(username) > 30:
            return Response(
                {
                    "status": True,
                    "message": "Username cannot exceed 30 characters",
                    "data": {
                        "available": False,
                        "username": username,
                        "message": "Username cannot exceed 30 characters",
                    },
                }
            )

        if not username.replace("_", "").replace(".", "").isalnum():
            return Response(
                {
                    "status": True,
                    "message": "Username can only contain letters, numbers, underscores and dots",
                    "data": {
                        "available": False,
                        "username": username,
                        "message": "Username can only contain letters, numbers, underscores and dots",
                    },
                }
            )

        user = UserService.get_user_by_username(username)
        available = user is None
        message = "Username is available" if available else "Username is taken"

        return Response(
            {
                "status": True,
                "message": message,
                "data": {
                    "available": available,
                    "username": username,
                    "message": message,
                },
            }
        )


class CheckEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["User's"],
        parameters=[
            OpenApiParameter(
                name="email", type=str, description="Email to check", required=True
            ),
        ],
        responses={200: CheckEmailResponseSerializer},
        examples=[
            OpenApiExample(
                "Email available",
                value={
                    "status": True,
                    "message": "Email is available",
                    "data": {
                        "available": True,
                        "email": "new@example.com",
                        "message": "Email is available",
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Email taken",
                value={
                    "status": True,
                    "message": "Email is already registered",
                    "data": {
                        "available": False,
                        "email": "existing@example.com",
                        "message": "Email is already registered",
                    },
                },
                response_only=True,
            ),
        ],
        description="Check if an email address is already registered.",
    )
    def get(self, request):
        email = request.query_params.get("email", "").strip().lower()
        if not email:
            return Response(
                {
                    "status": False,
                    "message": "Email is required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "@" not in email or "." not in email:
            return Response(
                {
                    "status": True,
                    "message": "Invalid email format",
                    "data": {
                        "available": False,
                        "email": email,
                        "message": "Invalid email format",
                    },
                }
            )

        user = UserService.get_user_by_email(email)
        available = user is None
        message = "Email is available" if available else "Email is already registered"

        return Response(
            {
                "status": True,
                "message": message,
                "data": {
                    "available": available,
                    "email": email,
                    "message": message,
                },
            }
        )


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["User's"],
        request=ResendSerializer,
        responses={200: ResendVerificationResponseSerializer},
    )
    @transaction.atomic
    def post(self, request):
        serializer = ResendSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data.get('email')
        user_id = serializer.validated_data.get('user_id')

        try:
            if email:
                user = User.objects.get(email=email)
            else:
                user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_active:
            return Response(
                {
                    "status": False,
                    "message": "User already active",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from users.services.otp_request import OtpRequestService
            from notifications.services.notification_queue import NotificationQueueService

            otp_request = OtpRequestService.create_otp_request(
                user=user,
                email=user.email,
                expires_in_minutes=10,
                otp_type="email"
            )
            NotificationQueueService.queue_notification(
                channel="email",
                recipient=user.email,
                subject="Email Verification",
                message=f"Your verification code is: {otp_request.otp_code}",
                metadata={"otp_code": otp_request.otp_code, "user_id": user.id}
            )
            return Response(
                {
                    "status": True,
                    "message": "Verification email sent",
                    "data": {"message": "Verification email sent"},
                }
            )
        except Exception as e:
            logger.exception("Error resending verification email")
            return Response(
                {
                    "status": False,
                    "message": "Failed to send verification email",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EmailVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["User's"],
        request=VerifyEmailSerializer,
        responses={200: EmailVerificationResponseSerializer},
        description="Verify email using OTP sent during registration.",
    )
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Invalid credentials",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_id = serializer.validated_data['user_id']
        otp_code = serializer.validated_data['otp_code']

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        from users.services.otp_request import OtpRequestService
        from notifications.services.notification_queue import NotificationQueueService

        otp_request = OtpRequestService.validate_otp(
            otp_code=otp_code,
            user=user,
        )
        if not otp_request:
            return Response(
                {
                    "status": False,
                    "message": "Invalid or expired OTP",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        OtpRequestService.mark_otp_used(otp_request)

        user.is_active = True
        user.is_verified = True
        user.save()

        NotificationQueueService.queue_notification(
            channel="email",
            recipient=user.email,
            subject="Welcome!",
            message="Your account has been successfully activated.",
        )

        return Response(
            {
                "status": True,
                "message": "Email verified successfully",
                "data": {"message": "Email verified successfully"},
            }
        )
        
        


# ----------------------------------------------------------------------
# Individual field update views (for profile details screen)
# ----------------------------------------------------------------------

class UpdateUsernameView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UpdateUsernameInputSerializer(serializers.Serializer):
        username = serializers.CharField(max_length=30, min_length=3)

        def validate_username(self, value):
            value = value.lower().strip()
            # Check format
            if not value.replace("_", "").replace(".", "").isalnum():
                raise serializers.ValidationError(
                    "Username can only contain letters, numbers, underscores and dots"
                )
            # Check uniqueness (exclude current user)
            if User.objects.filter(username__iexact=value).exclude(id=self.context['user'].id).exists():
                raise serializers.ValidationError("Username already taken")
            return value

    class ResponseData(serializers.Serializer):
        username = serializers.CharField()

    @extend_schema(
        tags=["User's"],
        request=UpdateUsernameInputSerializer,
        responses={200: UserUpdateResponseSerializer},
        description="Update the authenticated user's username.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = self.UpdateUsernameInputSerializer(data=request.data, context={'user': request.user})
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_username = serializer.validated_data['username']
        request.user.username = new_username
        request.user.save(update_fields=['username'])

        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action="update_username",
            description=f"Username changed to {new_username}",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        return Response(
            {
                "status": True,
                "message": "Username updated successfully",
                "data": {"user": UserProfileSerializer(request.user, context={"request": request}).data},
            }
        )


class UpdateEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UpdateEmailInputSerializer(serializers.Serializer):
        email = serializers.EmailField()

        def validate_email(self, value):
            value = value.lower().strip()
            if User.objects.filter(email__iexact=value).exclude(id=self.context['user'].id).exists():
                raise serializers.ValidationError("Email already registered")
            return value

    class ResponseData(serializers.Serializer):
        email = serializers.EmailField()

    @extend_schema(
        tags=["User's"],
        request=UpdateEmailInputSerializer,
        responses={200: UserUpdateResponseSerializer},
        description="Update the authenticated user's email address. Note: The user may need to re-verify the new email.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = self.UpdateEmailInputSerializer(data=request.data, context={'user': request.user})
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_email = serializer.validated_data['email']
        # Optionally set is_verified = False and send verification email
        request.user.email = new_email
        request.user.is_verified = False
        request.user.save(update_fields=['email', 'is_verified'])

        # Queue a new verification email (optional)
        try:
            from users.services.otp_request import OtpRequestService
            from notifications.services.notification_queue import NotificationQueueService
            otp_request = OtpRequestService.create_otp_request(
                user=request.user,
                email=new_email,
                expires_in_minutes=10,
                otp_type="email"
            )
            NotificationQueueService.queue_notification(
                channel="email",
                recipient=new_email,
                subject="Verify your new email address",
                message=f"Your verification code is: {otp_request.otp_code}",
                metadata={"otp_code": otp_request.otp_code, "user_id": request.user.id}
            )
        except Exception as e:
            logger.exception("Failed to send email verification after email update")

        UserActivity.objects.create(
            user=request.user,
            action="update_email",
            description=f"Email changed to {new_email}",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        return Response(
            {
                "status": True,
                "message": "Email updated successfully. Please verify your new email address.",
                "data": {"user": UserProfileSerializer(request.user, context={"request": request}).data},
            }
        )


class UpdateFirstNameView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UpdateFirstNameUpdateFirstNameInputSerializer(serializers.Serializer):
        first_name = serializers.CharField(max_length=30, allow_blank=True)

    @extend_schema(
        tags=["User's"],
        request=UpdateFirstNameUpdateFirstNameInputSerializer,
        responses={200: UserUpdateResponseSerializer},
        description="Update the authenticated user's first name.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = self.UpdateFirstNameUpdateFirstNameInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": False, "message": "Validation error", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.first_name = serializer.validated_data['first_name']
        request.user.save(update_fields=['first_name'])
        return Response(
            {
                "status": True,
                "message": "First name updated",
                "data": {"user": UserProfileSerializer(request.user, context={"request": request}).data},
            }
        )


class UpdateLastNameView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UpdateLastNameUpdateLastNameInputSerializer(serializers.Serializer):
        last_name = serializers.CharField(max_length=30, allow_blank=True)

    @extend_schema(
        tags=["User's"],
        request=UpdateLastNameUpdateLastNameInputSerializer,
        responses={200: UserUpdateResponseSerializer},
        description="Update the authenticated user's last name.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = self.UpdateLastNameUpdateLastNameInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": False, "message": "Validation error", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.last_name = serializer.validated_data['last_name']
        request.user.save(update_fields=['last_name'])
        return Response(
            {
                "status": True,
                "message": "Last name updated",
                "data": {"user": UserProfileSerializer(request.user, context={"request": request}).data},
            }
        )


class UpdatePhoneNumberView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UpdatePhoneNumberUpdatePhoneNumberInputSerializer(serializers.Serializer):
        phone_number = serializers.CharField(max_length=20, allow_blank=True, required=False)

    @extend_schema(
        tags=["User's"],
        request=UpdatePhoneNumberUpdatePhoneNumberInputSerializer,
        responses={200: UserUpdateResponseSerializer},
        description="Update the authenticated user's phone number.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = self.UpdatePhoneNumberUpdatePhoneNumberInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": False, "message": "Validation error", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.phone_number = serializer.validated_data.get('phone_number', '')
        request.user.save(update_fields=['phone_number'])
        return Response(
            {
                "status": True,
                "message": "Phone number updated",
                "data": {"user": UserProfileSerializer(request.user, context={"request": request}).data},
            }
        )


class UpdateBioView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UpdateBioUpdateBioInputSerializer(serializers.Serializer):
        bio = serializers.CharField(max_length=500, allow_blank=True, required=False)

    @extend_schema(
        tags=["User's"],
        request=UpdateBioUpdateBioInputSerializer,
        responses={200: UserUpdateResponseSerializer},
        description="Update the authenticated user's bio.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = self.UpdateBioUpdateBioInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": False, "message": "Validation error", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.bio = serializer.validated_data.get('bio', '')
        request.user.save(update_fields=['bio'])
        return Response(
            {
                "status": True,
                "message": "Bio updated",
                "data": {"user": UserProfileSerializer(request.user, context={"request": request}).data},
            }
        )


class UpdateLocationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UpdateLocationUpdateLocationInputSerializer(serializers.Serializer):
        location = serializers.CharField(max_length=100, allow_blank=True, required=False)

    @extend_schema(
        tags=["User's"],
        request=UpdateLocationUpdateLocationInputSerializer,
        responses={200: UserUpdateResponseSerializer},
        description="Update the authenticated user's location.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = self.UpdateLocationUpdateLocationInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": False, "message": "Validation error", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.location = serializer.validated_data.get('location', '')
        request.user.save(update_fields=['location'])
        return Response(
            {
                "status": True,
                "message": "Location updated",
                "data": {"user": UserProfileSerializer(request.user, context={"request": request}).data},
            }
        )


class UpdateDateOfBirthView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UpdateDateOfBirthUpdateDateOfBirthInputSerializer(serializers.Serializer):
        date_of_birth = serializers.DateField(required=False, allow_null=True)

        def validate_date_of_birth(self, value):
            if value:
                min_age_date = timezone.now().date() - timezone.timedelta(days=365 * 13)
                if value > min_age_date:
                    raise serializers.ValidationError("You must be at least 13 years old")
            return value

    @extend_schema(
        tags=["User's"],
        request=UpdateDateOfBirthUpdateDateOfBirthInputSerializer,
        responses={200: UserUpdateResponseSerializer},
        description="Update the authenticated user's date of birth.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = self.UpdateDateOfBirthUpdateDateOfBirthInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": False, "message": "Validation error", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.date_of_birth = serializer.validated_data.get('date_of_birth')
        request.user.save(update_fields=['date_of_birth'])
        return Response(
            {
                "status": True,
                "message": "Date of birth updated",
                "data": {"user": UserProfileSerializer(request.user, context={"request": request}).data},
            }
        )
        
# =========================== NEW ============================================================================

# ------------------- Response Serializers for NameEditStatus -------------------
class NameEditStatusDataSerializer(serializers.Serializer):
    can_edit = serializers.BooleanField()
    next_edit_available_at = serializers.CharField(allow_null=True, required=False)
    days_remaining = serializers.IntegerField(allow_null=True, required=False)
    cooldown_period_days = serializers.IntegerField()

class NameEditStatusResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = NameEditStatusDataSerializer()

# ------------------- Response Serializers for UpdateFullName -------------------
class UpdateFullNameResponseDataSerializer(serializers.Serializer):
    user = serializers.DictField()  # You can use UserProfileSerializer here if imported

class UpdateFullNameResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UpdateFullNameResponseDataSerializer()

# ------------------- Views -------------------
class NameEditStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        responses={
            200: NameEditStatusResponseSerializer,
        },
        description="Get the current user's name edit status including cooldown information.",
    )
    def get(self, request):
        user = request.user
        cooldown_days = getattr(settings, 'NAME_CHANGE_COOLDOWN_DAYS', 30)
        now = timezone.now()

        if user.last_name_change_date:
            next_available = user.last_name_change_date + timedelta(days=cooldown_days)
            if now >= next_available:
                can_edit = True
                days_remaining = 0
                next_edit_available_at = None
            else:
                can_edit = False
                delta = next_available - now
                days_remaining = delta.days
                next_edit_available_at = next_available.isoformat()
        else:
            can_edit = True
            days_remaining = 0
            next_edit_available_at = None

        data = {
            "can_edit": can_edit,
            "next_edit_available_at": next_edit_available_at,
            "days_remaining": days_remaining,
            "cooldown_period_days": cooldown_days,
        }

        return Response({
            "status": True,
            "message": "Name edit status retrieved",
            "data": data
        })


class UpdateFullNameView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UpdateFullNameInputSerializer(serializers.Serializer):
        first_name = serializers.CharField(max_length=30, required=True)
        middle_name = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True)
        last_name = serializers.CharField(max_length=30, required=True)

    @extend_schema(
        tags=["User's"],
        request=UpdateFullNameInputSerializer,
        responses={
            200: UpdateFullNameResponseSerializer,
            400: UpdateFullNameResponseSerializer,
        },
        description="Update the user's full name (first, middle, last). Respects cooldown period.",
    )
    @transaction.atomic
    def put(self, request):
        serializer = self.UpdateFullNameInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": False, "message": "Validation error", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        user = request.user
        cooldown_days = getattr(settings, 'NAME_CHANGE_COOLDOWN_DAYS', 30)

        # Check cooldown
        if user.last_name_change_date:
            next_available = user.last_name_change_date + timedelta(days=cooldown_days)
            if timezone.now() < next_available:
                days_left = (next_available - timezone.now()).days
                return Response(
                    {
                        "status": False,
                        "message": f"You can change your name again after {days_left} days.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Update name fields
        user.first_name = data['first_name'].strip()
        user.middle_name = data.get('middle_name', '').strip() or None
        user.last_name = data['last_name'].strip()
        user.last_name_change_date = timezone.now()
        user.save(update_fields=['first_name', 'middle_name', 'last_name', 'last_name_change_date'])

        # Log activity (optional)
        from users.models.user_activity import UserActivity
        UserActivity.objects.create(
            user=user,
            action="update_full_name",
            description=f"Name changed to {user.first_name} {user.middle_name or ''} {user.last_name}".strip(),
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        from users.serializers.user.profile import UserProfileSerializer
        user_data = UserProfileSerializer(user, context={"request": request}).data

        return Response(
            {
                "status": True,
                "message": "Full name updated successfully",
                "data": {"user": user_data},
            }
        )