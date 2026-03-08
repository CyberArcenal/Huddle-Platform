# accounts/views/password_reset.py
from datetime import timedelta
import uuid
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.contrib.auth.hashers import make_password
from rest_framework.permissions import AllowAny
import logging
from global_utils.security import get_client_ip
from notifications.utils.email import get_dynamic_email_backend
from users.models.base import LoginCheckpoint, OtpRequest, User
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiTypes
from users.serializers.auth import (
    PasswordResetCompleteRequestSerializer,
    PasswordResetCompleteResponseSerializer,
    PasswordResetRequestResponseSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifyRequestSerializer,
    PasswordResetVerifyResponseSerializer,
)

logger = logging.getLogger(__name__)

from django.utils import timezone
from datetime import timedelta
import secrets


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={
            200: PasswordResetRequestResponseSerializer,
            400: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Password reset request",
                value={"email": "john@example.com"},
                request_only=True,
            ),
            OpenApiExample(
                "Password reset request successful",
                value={
                    "message": "If the email exists, a password reset OTP has been sent"
                },
                response_only=True,
            ),
        ],
        description="Request a password reset OTP to be sent to the user's email.",
    )
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"message": "Email is required"}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Always generic response
            return Response(
                {"message": "If the email exists, a password reset OTP has been sent"},
                status=200,
            )

        if not user.is_active:
            return Response({"message": "Account is deactivated"}, status=400)

        # Check existing OTP
        existing = (
            OtpRequest.objects.filter(email=email, user=user)
            .order_by("-created_at")
            .first()
        )
        now = timezone.now()

        if existing and not existing.is_used and existing.expires_at > now:
            # Still valid, don't create new
            return Response(
                {"message": "If the email exists, a password reset OTP has been sent"},
                status=200,
            )

        # Generate new OTP
        otp_code = str(secrets.randbelow(900000) + 100000)
        expires_at = now + timedelta(minutes=15)

        get_dynamic_email_backend()

        OtpRequest.objects.create(
            email=email,
            user=user,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False,
            attempt_count=0,
        )

        return Response(
            {"message": "If the email exists, a password reset OTP has been sent"},
            status=200,
        )


class PasswordResetVerifyView(APIView):
    """
    Verify the OTP for password reset
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetVerifyRequestSerializer,
        responses={
            200: PasswordResetVerifyResponseSerializer,
            400: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Password reset verify request",
                value={"email": "john@example.com", "otp_code": "123456"},
                request_only=True,
            ),
            OpenApiExample(
                "Password reset verify successful",
                value={
                    "message": "OTP verified successfully",
                    "email": "john@example.com",
                    "verified": True,
                    "checkpoint_token": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                },
                response_only=True,
            ),
        ],
        description="Verify the OTP for password reset and obtain a checkpoint token to complete the reset.",
    )
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        email = request.data.get("email")
        otp_code = request.data.get("otp_code")

        if not email or not otp_code:
            return Response(
                {"detail": "Email and OTP code are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            otp_record = (
                OtpRequest.objects.filter(email=email)
                .order_by("-created_at")  # assumes you have created_at field
                .first()
            )

            # Check if OTP is expired
            if timezone.now() > otp_record.expires_at:
                return Response(
                    {"detail": "OTP has expired"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Check if OTP is already used
            if otp_record.is_used:
                return Response(
                    {"detail": "OTP has already been used"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if too many attempts
            if otp_record.attempt_count >= 3:
                return Response(
                    {"detail": "Too many failed attempts"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verify OTP
            if otp_record.otp_code != otp_code:
                otp_record.attempt_count += 1
                otp_record.save()
                return Response(
                    {"detail": "Invalid OTP code"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Mark OTP as used
            otp_record.is_used = True
            otp_record.save()

            # Generate a short-lived token for password reset completion
            checkpoint_token = str(uuid.uuid4())
            expires_at = timezone.now() + timedelta(
                minutes=10
            )  # Short expiration for security
            LoginCheckpoint.objects.create(
                user=otp_record.user, token=checkpoint_token, expires_at=expires_at
            )

            return Response(
                {
                    "message": "OTP verified successfully",
                    "email": email,
                    "verified": True,
                    "checkpoint_token": checkpoint_token,
                },
                status=status.HTTP_200_OK,
            )

        except OtpRequest.DoesNotExist:
            return Response(
                {"detail": "No OTP found for this email"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PasswordResetCompleteView(APIView):
    permission_classes = [AllowAny]
    """
    Complete password reset with a new password
    """

    @extend_schema(
        request=PasswordResetCompleteRequestSerializer,
        responses={
            200: PasswordResetCompleteResponseSerializer,
            400: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Password reset complete request",
                value={
                    "checkpoint_token": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                    "new_password": "NewSecurePass123!",
                    "confirm_password": "NewSecurePass123!",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Password reset complete successful",
                value={"message": "Password reset successfully"},
                response_only=True,
            ),
        ],
        description="Complete password reset using the checkpoint token and new password.",
    )
    @transaction.atomic
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        checkpoint_token = request.data.get("checkpoint_token")
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if not checkpoint_token or not new_password or not confirm_password:
            return Response(
                {
                    "detail": "Checkpoint token, new password and confirmation are required"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_password != confirm_password:
            return Response(
                {"detail": "Passwords do not match"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Validate checkpoint
            checkpoint = LoginCheckpoint.objects.get(token=checkpoint_token)
            if not checkpoint.is_valid:
                return Response(
                    {"detail": "Invalid or expired checkpoint token"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = checkpoint.user

            # Update password
            user.password = make_password(new_password)
            user.save()

            # Mark checkpoint as used
            checkpoint.is_used = True
            checkpoint.save()

            return Response(
                {"message": "Password reset successfully"}, status=status.HTTP_200_OK
            )

        except LoginCheckpoint.DoesNotExist:
            return Response(
                {"detail": "Invalid checkpoint token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.error(f"Password reset failed: {exc}")

            return Response(
                {"detail": "An error occurred during password reset"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
