# accounts/views/password_recover.py
from datetime import timedelta
import uuid
import secrets
import logging
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.db import transaction
from django.contrib.auth.hashers import make_password
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiTypes
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers

from global_utils.security import get_client_ip
from notifications.utils.email import get_dynamic_email_backend
from users.models import LoginCheckpoint, OtpRequest, User
from users.serializers.auth import (
    PasswordResetRequestSerializer,
    PasswordResetVerifyRequestSerializer,
    PasswordResetCompleteRequestSerializer,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class PasswordResetRequestResponseData(serializers.Serializer):
    pass  # walang data, message lang


class PasswordResetRequestResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PasswordResetRequestResponseData(allow_null=True)


class PasswordResetVerifyResponseData(serializers.Serializer):
    email = serializers.EmailField()
    verified = serializers.BooleanField()
    checkpoint_token = serializers.CharField()


class PasswordResetVerifyResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PasswordResetVerifyResponseData()


class PasswordResetCompleteResponseData(serializers.Serializer):
    pass


class PasswordResetCompleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PasswordResetCompleteResponseData(allow_null=True)


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class PasswordResetRequestView(APIView):
    """
    Request a password reset OTP to be sent to the user's email.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Password Recovery"],
        request=PasswordResetRequestSerializer,
        responses={200: PasswordResetRequestResponseSerializer},
        examples=[
            OpenApiExample(
                "Request",
                value={"email": "john@example.com"},
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "status": True,
                    "message": "If the email exists, a password reset OTP has been sent",
                    "data": None,
                },
                response_only=True,
            ),
        ],
        description="Request a password reset OTP to be sent to the user's email.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Generic response for security
            return Response(
                {
                    "status": True,
                    "message": "If the email exists, a password reset OTP has been sent",
                    "data": None,
                },
                status=status.HTTP_200_OK,
            )

        if not user.is_active:
            return Response(
                {
                    "status": False,
                    "message": "Account is deactivated",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check existing OTP
        existing = (
            OtpRequest.objects.filter(email=email, user=user)
            .order_by("-created_at")
            .first()
        )
        now = timezone.now()

        if existing and not existing.is_used and existing.expires_at > now:
            # Still valid, do not create new
            return Response(
                {
                    "status": True,
                    "message": "If the email exists, a password reset OTP has been sent",
                    "data": None,
                },
                status=status.HTTP_200_OK,
            )

        # Generate new OTP
        otp_code = str(secrets.randbelow(900000) + 100000)
        expires_at = now + timedelta(minutes=15)

        try:
            get_dynamic_email_backend()  # Initialize email backend (optional)
            # TODO: Send email with OTP code
        except Exception as e:
            logger.error(f"Failed to send OTP email to {email}: {e}")

        OtpRequest.objects.create(
            email=email,
            user=user,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False,
            attempt_count=0,
            type="email",
        )

        return Response(
            {
                "status": True,
                "message": "If the email exists, a password reset OTP has been sent",
                "data": None,
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetVerifyView(APIView):
    """
    Verify the OTP for password reset and obtain a checkpoint token.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Password Recovery"],
        request=PasswordResetVerifyRequestSerializer,
        responses={200: PasswordResetVerifyResponseSerializer},
        examples=[
            OpenApiExample(
                "Verify request",
                value={"email": "john@example.com", "otp_code": "123456"},
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "status": True,
                    "message": "OTP verified successfully",
                    "data": {
                        "email": "john@example.com",
                        "verified": True,
                        "checkpoint_token": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                    },
                },
                response_only=True,
            ),
        ],
        description="Verify the OTP for password reset and obtain a checkpoint token to complete the reset.",
    )
    @transaction.atomic
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        serializer = PasswordResetVerifyRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data["email"]
        otp_code = serializer.validated_data["otp_code"]

        try:
            otp_record = (
                OtpRequest.objects.filter(email=email)
                .order_by("-created_at")
                .first()
            )

            if not otp_record:
                return Response(
                    {
                        "status": False,
                        "message": "No OTP found for this email",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check expiration
            if timezone.now() > otp_record.expires_at:
                return Response(
                    {
                        "status": False,
                        "message": "OTP has expired",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if already used
            if otp_record.is_used:
                return Response(
                    {
                        "status": False,
                        "message": "OTP has already been used",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check attempt limit
            if otp_record.attempt_count >= 3:
                return Response(
                    {
                        "status": False,
                        "message": "Too many failed attempts",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verify OTP
            if otp_record.otp_code != otp_code:
                otp_record.attempt_count += 1
                otp_record.save()
                return Response(
                    {
                        "status": False,
                        "message": "Invalid OTP code",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Mark OTP as used
            otp_record.is_used = True
            otp_record.save()

            # Generate short-lived checkpoint token
            checkpoint_token = str(uuid.uuid4())
            expires_at = timezone.now() + timedelta(minutes=10)
            LoginCheckpoint.objects.create(
                user=otp_record.user,
                token=checkpoint_token,
                expires_at=expires_at,
                is_used=False,
            )

            return Response(
                {
                    "status": True,
                    "message": "OTP verified successfully",
                    "data": {
                        "email": email,
                        "verified": True,
                        "checkpoint_token": checkpoint_token,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("PasswordResetVerifyView error")
            return Response(
                {
                    "status": False,
                    "message": "An error occurred during verification",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PasswordResetCompleteView(APIView):
    """
    Complete password reset using the checkpoint token and new password.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Password Recovery"],
        request=PasswordResetCompleteRequestSerializer,
        responses={200: PasswordResetCompleteResponseSerializer},
        examples=[
            OpenApiExample(
                "Complete request",
                value={
                    "checkpoint_token": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                    "new_password": "NewSecurePass123!",
                    "confirm_password": "NewSecurePass123!",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "status": True,
                    "message": "Password reset successfully",
                    "data": None,
                },
                response_only=True,
            ),
        ],
        description="Complete password reset using the checkpoint token and new password.",
    )
    @transaction.atomic
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        serializer = PasswordResetCompleteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        checkpoint_token = serializer.validated_data["checkpoint_token"]
        new_password = serializer.validated_data["new_password"]

        try:
            checkpoint = LoginCheckpoint.objects.get(token=checkpoint_token)

            if not checkpoint.is_valid:
                return Response(
                    {
                        "status": False,
                        "message": "Invalid or expired checkpoint token",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = checkpoint.user

            # Update password
            user.password = make_password(new_password)
            user.save()

            # Mark checkpoint as used
            checkpoint.is_used = True
            checkpoint.save()

            # Optional: Log security event
            # SecurityLog.objects.create(...)

            return Response(
                {
                    "status": True,
                    "message": "Password reset successfully",
                    "data": None,
                },
                status=status.HTTP_200_OK,
            )

        except LoginCheckpoint.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Invalid checkpoint token",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("PasswordResetCompleteView error")
            return Response(
                {
                    "status": False,
                    "message": "An error occurred during password reset",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )