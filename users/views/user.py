from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from core.settings.dev import LOGGER
from global_utils.pagination import UsersPagination
from users.serializers.user.profile import UserProfileSerializer

from ..services.user import UserService
from ..services.security_log import SecurityLogService
from ..services.login_session import LoginSessionService
from ..serializers.user.base import (
    UserCreateSerializer,
    UserProfileSchemaUpdateSerializer,
    UserRegisterSerializer,
    UserUpdateSerializer,
    UserListSerializer,
    UserStatusSerializer,
)
from ..models import User, UserStatus
from rest_framework import serializers
from ..serializers.user.base import UserListSerializer


# ----- Paginated response serializers for drf-spectacular -----
class PaginatedUserListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserListSerializer(many=True)


# ----- New input serializer for UserDeactivateView -----
class UserDeactivateInputSerializer(serializers.Serializer):
    password = serializers.CharField(
        write_only=True, help_text="Current password for confirmation"
    )
    confirm = serializers.BooleanField(help_text="Must be true to confirm deactivation")


# -------------------------------------------------------
class UserRegisterResponse(serializers.Serializer):
    message = serializers.StringRelatedField()
    user = UserProfileSerializer(read_only=True)


# users/views/user.py

from users.services.otp_request import OtpRequestService
from notifications.services.notification_queue import NotificationQueueService

from users.services.otp_request import OtpRequestService
from notifications.services.notification_queue import NotificationQueueService

# users/views/user.py

class UserRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["User's"],
        request=UserRegisterSerializer,
        responses={201: serializers.DictField()},
        description="Register a new user or resend verification for inactive accounts.",
    )
    @transaction.atomic
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        existing_user = UserService.get_user_by_email(email)

        # Handle existing inactive user (resend OTP)
        if existing_user and not existing_user.is_active:
            try:
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
                        "message": "Account not yet verified. A new verification email has been sent.",
                        "user_id": existing_user.id,
                    },
                    status=status.HTTP_200_OK
                )
            except Exception as e:
                LOGGER.exception("Failed to resend OTP for inactive user")
                return Response(
                    {"error": "Failed to send verification email. Please try again later."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # If existing user is active, return error
        if existing_user and existing_user.is_active:
            return Response(
                {"error": "Email already registered."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # New user: validate and create
        serializer = UserRegisterSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            try:
                with transaction.atomic():
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
                            "message": "Verification email sent. Please check your inbox.",
                            "user_id": user.id,
                        },
                        status=status.HTTP_201_CREATED,
                    )
            except Exception as e:
                LOGGER.exception("Registration failed for new user")
                return Response(
                    {"error": "Registration failed. Please try again later."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            # Validation errors from the serializer
            return Response(
                {"error": "Validation failed", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserProfileResponse(serializers.Serializer):
    message = serializers.StringRelatedField()
    user = UserProfileSerializer(read_only=True)


class UserProfileView(APIView):
    """View for user profile operations"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        responses={200: UserProfileSerializer},
        description="Get the profile of the currently authenticated user.",
    )
    def get(self, request):
        serializer = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["User's"],
        request=UserProfileSchemaUpdateSerializer,
        responses={200: UserProfileResponse},
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
                        "message": "Profile updated successfully",
                        "user": data,
                    }
                )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class UserDetailView(APIView):
    """View for retrieving specific user profiles"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        responses={200: UserProfileSerializer},
        description="Retrieve a user's public profile by ID.",
    )
    def get(self, request, user_id):
        try:
            user = UserService.get_user_by_id(user_id)

            if not user or user.status != UserStatus.ACTIVE:
                return Response(
                    {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )

            serializer = UserProfileSerializer(user, context={"request": request})
            return Response(serializer.data)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserSearchView(APIView):
    """View for searching users"""

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
        responses={200: PaginatedUserListSerializer},
        description="Search users by username, first name, or last name.",
    )
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query or len(query) < 2:
            return Response(
                {"error": "Search query must be at least 2 characters"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            users = UserService.search_users(query)
            paginator = UsersPagination()
            page = paginator.paginate_queryset(users, request)
            serializer = UserListSerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserStatusUpdateResponse(serializers.Serializer):
    message = serializers.StringRelatedField()
    user_id = serializers.IntegerField()
    status = serializers.StringRelatedField()


class UserStatusUpdateView(APIView):
    """View for updating user status (admin/self)"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        request=UserStatusSerializer,
        responses={200: UserStatusUpdateResponse},
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
                        {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
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
                        "message": f"User status updated to {updated_user.status}",
                        "user_id": updated_user.id,
                        "status": updated_user.status,
                    }
                )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class UserDeactivateView(APIView):
    """View for deactivating user account"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        request=UserDeactivateInputSerializer,
        responses={200: UserStatusUpdateResponse},
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
            return Response(input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = input_serializer.validated_data
        password = data["password"]
        confirm = data["confirm"]

        if not request.user.check_password(password):
            return Response(
                {"error": "Invalid password"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not confirm:
            return Response(
                {"error": "Please confirm deactivation"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
                "message": "Account deactivated successfully",
                "user_id": user.id,
                "status": user.status,
            }
        )


class VerifyUserResponse(serializers.Serializer):
    message = serializers.StringRelatedField()
    user_id = serializers.IntegerField()
    is_verified = serializers.BooleanField()


class VerifyUserView(APIView):
    """View for verifying user account"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User's"],
        responses={200: VerifyUserResponse},
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
                    "message": "Account verified successfully",
                    "user_id": user.id,
                    "is_verified": user.is_verified,
                }
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CheckUsernameResponse(serializers.Serializer):
    available = serializers.BooleanField()
    username = serializers.StringRelatedField()
    message = serializers.StringRelatedField()


class CheckUsernameView(APIView):
    """View for checking username availability"""

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
        responses={200: CheckUsernameResponse},
        examples=[
            OpenApiExample(
                "Username available",
                value={
                    "available": True,
                    "username": "newuser",
                    "message": "Username is available",
                },
                response_only=True,
            ),
            OpenApiExample(
                "Username taken",
                value={
                    "available": False,
                    "username": "existing",
                    "message": "Username is taken",
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
                {"error": "Username is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        if len(username) < 3:
            return Response(
                {
                    "available": False,
                    "message": "Username must be at least 3 characters",
                }
            )

        if len(username) > 30:
            return Response(
                {"available": False, "message": "Username cannot exceed 30 characters"}
            )

        if not username.replace("_", "").replace(".", "").isalnum():
            return Response(
                {
                    "available": False,
                    "message": "Username can only contain letters, numbers, underscores and dots",
                }
            )

        user = UserService.get_user_by_username(username)
        available = user is None

        return Response(
            {
                "available": available,
                "username": username,
                "message": (
                    "Username is available" if available else "Username is taken"
                ),
            }
        )


class CheckEmailResponse(serializers.Serializer):
    available = serializers.BooleanField()
    email = serializers.StringRelatedField()
    message = serializers.StringRelatedField()


class CheckEmailView(APIView):
    """View for checking email availability"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["User's"],
        parameters=[
            OpenApiParameter(
                name="email", type=str, description="Email to check", required=True
            ),
        ],
        responses={200: CheckEmailResponse},
        examples=[
            OpenApiExample(
                "Email available",
                value={
                    "available": True,
                    "email": "new@example.com",
                    "message": "Email is available",
                },
                response_only=True,
            ),
            OpenApiExample(
                "Email taken",
                value={
                    "available": False,
                    "email": "existing@example.com",
                    "message": "Email is already registered",
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
                {"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        if "@" not in email or "." not in email:
            return Response({"available": False, "message": "Invalid email format"})

        user = UserService.get_user_by_email(email)
        available = user is None

        return Response(
            {
                "available": available,
                "email": email,
                "message": (
                    "Email is available" if available else "Email is already registered"
                ),
            }
        )





class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    class ResendSerializer(serializers.Serializer):
        email = serializers.EmailField(required=False)
        user_id = serializers.IntegerField(required=False)

        def validate(self, attrs):
            if not attrs.get('email') and not attrs.get('user_id'):
                raise serializers.ValidationError("Either email or user_id is required")
            return attrs
    
    class ResendVerificationResponse(serializers.Serializer):
        status = serializers.BooleanField()
        message = serializers.StringRelatedField(allow_null=True)
        error = serializers.StringRelatedField(allow_null=True)


    @extend_schema(
        tags=["User's"],
        request=ResendSerializer,
        responses={200: ResendVerificationResponse},
    )
    @transaction.atomic
    def post(self, request):
        serializer = self.ResendSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data.get('email')
        user_id = serializer.validated_data.get('user_id')

        try:
            if email:
                user = User.objects.get(email=email)
            else:
                user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"status": False, "error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        if user.is_active:
            return Response({"status": False, "error": "User already active"}, status=status.HTTP_400_BAD_REQUEST)

        # Create new OTP request
        otp_request = OtpRequestService.create_otp_request(
            user=user,
            email=user.email,
            expires_in_minutes=10,
            otp_type="email"
        )

        # Queue notification
        NotificationQueueService.queue_notification(
            channel="email",
            recipient=user.email,
            subject="Email Verification",
            message=f"Your verification code is: {otp_request.otp_code}",
            metadata={"otp_code": otp_request.otp_code, "user_id": user.id}
        )

        return Response({"status": True, "message": "Verification email sent"})


class EmailVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    class VerifyEmailSerializer(serializers.Serializer):
        user_id = serializers.IntegerField(required=True)
        otp_code = serializers.CharField(max_length=6, min_length=6, required=True)
    
    class VerifyEmailResponse(serializers.Serializer):
        status = serializers.BooleanField()
        message = serializers.StringRelatedField(allow_null=True)
        error = serializers.StringRelatedField(allow_null=True)

    @extend_schema(
        tags=["User's"],
        request=VerifyEmailSerializer,
        responses={200: VerifyEmailResponse},
        description="Verify email using OTP sent during registration.",
    )
    def post(self, request):
        serializer = self.VerifyEmailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": False, "error": "Invalid credentials"}, status=status.HTTP_400_BAD_REQUEST)

        user_id = serializer.validated_data['user_id']
        otp_code = serializer.validated_data['otp_code']

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"status": False, "error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # Validate OTP
        otp_request = OtpRequestService.validate_otp(
            otp_code=otp_code,
            user=user,
        )
        if not otp_request:
            return Response({"status": False, "error": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

        # Mark OTP as used
        OtpRequestService.mark_otp_used(otp_request)

        # Activate user
        user.is_active = True
        user.is_verified = True
        user.save()

        # Optionally, send welcome email
        NotificationQueueService.queue_notification(
            channel="email",
            recipient=user.email,
            subject="Welcome!",
            message="Your account has been successfully activated.",
        )

        return Response({"status": True, "message": "Email verified successfully"})