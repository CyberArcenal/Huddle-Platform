from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import UsersPagination

from ..services.user import UserService
from ..services.security_log import SecurityLogService
from ..services.login_session import LoginSessionService
from ..serializers.user import (
    UserCreateSerializer,
    UserUpdateSerializer,
    UserProfileSerializer,
    UserListSerializer,
    UserStatusSerializer,
)
from ..models import User, UserStatus
from rest_framework import serializers
from ..serializers.user import UserListSerializer


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


class UserRegisterView(APIView):
    """View for user registration"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=UserCreateSerializer,
        responses={201: UserProfileSerializer},
        examples=[
            OpenApiExample(
                "Registration request",
                value={
                    "username": "newuser",
                    "email": "user@example.com",
                    "password": "securepass123",
                    "first_name": "John",
                    "last_name": "Doe",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Registration response",
                value={
                    "id": 1,
                    "username": "newuser",
                    "email": "user@example.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "bio": "",
                    "profile_picture": None,
                    "cover_photo": None,
                    "date_of_birth": None,
                    "phone_number": "",
                    "is_verified": False,
                    "status": "active",
                    "created_at": "2025-03-07T12:34:56Z",
                    "updated_at": "2025-03-07T12:34:56Z",
                },
                response_only=True,
            ),
        ],
        description="Register a new user account.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = UserCreateSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                with transaction.atomic():
                    user = serializer.save()

                    SecurityLogService.create_log(
                        user=user,
                        event_type="signup",
                        ip_address=request.META.get("REMOTE_ADDR"),
                        user_agent=request.META.get("HTTP_USER_AGENT"),
                        details="User registered successfully",
                    )

                    response_serializer = UserProfileSerializer(
                        user, context={"request": request}
                    )
                    return Response(
                        {
                            "message": "User registered successfully",
                            "user": response_serializer.data,
                        },
                        status=status.HTTP_201_CREATED,
                    )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class UserProfileView(APIView):
    """View for user profile operations"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: UserProfileSerializer},
        description="Get the profile of the currently authenticated user.",
    )
    def get(self, request):
        serializer = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=UserUpdateSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "user": UserProfileSerializer().data,
                },
            }
        },
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

                return Response(
                    {
                        "message": "Profile updated successfully",
                        "user": UserProfileSerializer(
                            user, context={"request": request}
                        ).data,
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


class UserStatusUpdateView(APIView):
    """View for updating user status (admin/self)"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=UserStatusSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "user_id": {"type": "integer"},
                    "status": {"type": "string"},
                },
            }
        },
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
        request=UserDeactivateInputSerializer,  # ✅ Now using dedicated serializer
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "user_id": {"type": "integer"},
                    "status": {"type": "string"},
                },
            }
        },
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


class VerifyUserView(APIView):
    """View for verifying user account"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "user_id": {"type": "integer"},
                    "is_verified": {"type": "boolean"},
                },
            }
        },
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


class CheckUsernameView(APIView):
    """View for checking username availability"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="username",
                type=str,
                description="Username to check",
                required=True,
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "available": {"type": "boolean"},
                    "username": {"type": "string"},
                    "message": {"type": "string"},
                },
            }
        },
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


class CheckEmailView(APIView):
    """View for checking email availability"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="email", type=str, description="Email to check", required=True
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "available": {"type": "boolean"},
                    "email": {"type": "string"},
                    "message": {"type": "string"},
                },
            }
        },
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
