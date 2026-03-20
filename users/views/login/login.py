import logging
import uuid
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db.models import Q
from global_utils.security import get_client_ip
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import random
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import transaction
from users.enums import UserStatus
from users.models import (
    LoginCheckpoint,
    LoginSession,
    OtpRequest,
    SecurityLog,
    UserSecuritySettings,
)
from users.serializers.user import UserProfileSerializer
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiTypes
from users.serializers.auth import (
    LoginRequestSerializer,
    Verify2FARequestSerializer,
    Resend2FARequestSerializer,
    Verify2FAResponseSerializer,
    Resend2FAResponseSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginRequestSerializer,
        responses={
            200: OpenApiTypes.OBJECT,  # We'll handle two possible shapes via examples
            400: OpenApiTypes.OBJECT,
            401: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Login request",
                value={"email": "john@example.com", "password": "SecurePass123!"},
                request_only=True,
            ),
            OpenApiExample(
                "Login successful (no 2FA)",
                value={
                    "status": True,
                    "user": {
                        "id": 1,
                        "username": "johndoe",
                        "email": "john@example.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "profile_picture_url": "https://example.com/media/profile_pics/john.jpg",
                        "cover_photo_url": "https://example.com/media/covers/john_cover.jpg",
                        "bio": "Software developer",
                        "is_verified": True,
                        "followers_count": 42,
                        "following_count": 18,
                        "is_following": False,
                    },
                    "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc0MTU5NjAwMCwianRpIjoiMTIzYWJjIiwidXNlcl9pZCI6MX0...",
                    "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzQxNTk2MDAwLCJqdGkiOiI0NTZkZWYiLCJ1c2VyX2lkIjoxfQ...",
                    "expiresIn": 900,
                    "message": "Login successful",
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "2FA required",
                value={
                    "status": True,
                    "requires_2fa": True,
                    "checkpoint_token": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                    "message": "Two-factor authentication required. Please check your email for the verification code.",
                    "expires_in": 300,
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
        description="Authenticate user and return tokens. If 2FA is enabled, returns checkpoint_token.",
    )
    @transaction.atomic
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        device_name = user_agent[:100]
        logger.debug(
            f"Login request from IP: {client_ip}, User-Agent: {user_agent} body: {request.data}"
        )

        serializer = LoginRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        logger.info(f"Login attempt for email: {email} from IP: {client_ip}")

        try:
            user = User.objects.get(Q(username=email) | Q(email=email))
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "detail": "No Account found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.debug(f"User login request: {user}")
        if user.check_password(password):
            if user.status != UserStatus.ACTIVE:
                return Response(
                    {
                        "status": False,
                        "detail": f"Account status: {user.status}. Please contact administrator.",
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            security_settings, created = UserSecuritySettings.objects.get_or_create(
                user=user
            )

            if security_settings.two_factor_enabled:
                return self._initiate_2fa(
                    user, request, client_ip, user_agent, device_name
                )
            else:
                return self._complete_login(
                    user, request, client_ip, user_agent, device_name
                )
        else:
            return Response(
                {"status": False, "detail": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

    def _initiate_2fa(self, user, request, client_ip, user_agent, device_name):
        try:
            otp_code = f"{random.randint(0, 999999):06d}"
            checkpoint_token = uuid.uuid4()
            LoginCheckpoint.objects.create(
                user=user,
                email=user.email,
                token=checkpoint_token,
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            OtpRequest.objects.create(
                user=user,
                otp_code=otp_code,
                type=OtpRequest.EMAIL,
                email=user.email,
                expires_at=timezone.now() + timedelta(minutes=5),
            )
            logger.info(f"2FA OTP for {user.email}: {otp_code}")

            # Return using 2FA response serializer structure
            return Response(
                {
                    "status": True,
                    "requires_2fa": True,
                    "checkpoint_token": str(checkpoint_token),
                    "message": "Two-factor authentication required. Please check your email for the verification code.",
                    "expires_in": 300,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"Error initiating 2FA for user {user.id}: {str(e)}")
            return Response(
                {
                    "status": False,
                    "detail": "Error initiating two-factor authentication",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _complete_login(self, user, request, client_ip, user_agent, device_name):
        try:
            user.last_login = timezone.now()
            user.save()

            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
            refresh_token = refresh
            now_ts = int(timezone.now().timestamp())
            access_exp = int(refresh.access_token.payload["exp"])
            refresh_exp = int(refresh.payload["exp"])

            refresh_jti = refresh["jti"]
            access_jti = access_token["jti"]

            lifetime = settings.SIMPLE_JWT.get(
                "REFRESH_TOKEN_LIFETIME", timezone.timedelta(days=7)
            )
            expires_at = timezone.now() + lifetime

            LoginSession.objects.create(
                id=uuid.uuid4(),
                user=user,
                device_name=device_name,
                ip_address=client_ip,
                user_agent=user_agent,
                expires_at=expires_at,
                refresh_token=refresh_jti,
                access_token=access_jti,
            )

            SecurityLog.objects.create(
                user=user,
                event_type="login",
                ip_address=client_ip,
                user_agent=user_agent,
                details="User logged in successfully",
            )

            user_data = UserProfileSerializer(user).data
            logger.debug(f"User data: {user_data}")
            # Return using success response serializer structure
            return Response(
                {
                    "status": True,
                    "user": user_data,
                    "refreshToken": str(refresh),
                    "accessToken": str(access_token),
                    "expiresIn": access_exp,
                    "message": "Login successful",
                }
            )
        except Exception as e:
            logger.error(f"Error completing login for user {user.id}: {str(e)}")
            return Response(
                {"status": False, "detail": "Error completing login"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class Verify2FALoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=Verify2FARequestSerializer,
        responses={
            200: Verify2FAResponseSerializer,
            400: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Verify 2FA request",
                value={
                    "checkpoint_token": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                    "otp_code": "123456",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Verify 2FA successful",
                value={
                    "status": True,
                    "user": {
                        "id": 1,
                        "username": "johndoe",
                        "email": "john@example.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "profile_picture_url": "https://example.com/media/profile_pics/john.jpg",
                        "cover_photo_url": "https://example.com/media/covers/john_cover.jpg",
                        "bio": "Software developer",
                        "is_verified": True,
                        "followers_count": 42,
                        "following_count": 18,
                        "is_following": False,
                    },
                    "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc0MTU5NjAwMCwianRpIjoiMTIzYWJjIiwidXNlcl9pZCI6MX0...",
                    "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzQxNTk2MDAwLCJqdGkiOiI0NTZkZWYiLCJ1c2VyX2lkIjoxfQ...",
                    "expiresIn": 900,
                    "message": "Login successful with two-factor authentication",
                },
                response_only=True,
            ),
        ],
        description="Verify 2FA OTP and complete login.",
    )
    @transaction.atomic
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        device_name = user_agent[:100]

        serializer = Verify2FARequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        checkpoint_token = serializer.validated_data["checkpoint_token"]
        otp_code = serializer.validated_data["otp_code"]

        try:
            checkpoint = LoginCheckpoint.objects.filter(
                token=checkpoint_token, is_used=False, expires_at__gt=timezone.now()
            ).first()

            if not checkpoint:
                return Response(
                    {"status": False, "detail": "Invalid or expired checkpoint token"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = checkpoint.user

            otp = OtpRequest.objects.filter(
                user=user,
                otp_code=otp_code,
                type=OtpRequest.EMAIL,
                is_used=False,
                expires_at__gte=timezone.now(),
            ).first()

            if not otp:
                return Response(
                    {"status": False, "detail": "Invalid or expired OTP code"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            otp.is_used = True
            otp.save()

            checkpoint.is_used = True
            checkpoint.save()

            user.last_login = timezone.now()
            user.save()

            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
            refresh_token = refresh
            access_exp = int(refresh.access_token.payload["exp"])

            refresh_jti = refresh["jti"]
            access_jti = access_token["jti"]

            lifetime = settings.SIMPLE_JWT.get(
                "REFRESH_TOKEN_LIFETIME", timezone.timedelta(days=7)
            )
            expires_at = timezone.now() + lifetime

            LoginSession.objects.create(
                id=uuid.uuid4(),
                user=user,
                device_name=device_name,
                ip_address=client_ip,
                user_agent=user_agent,
                expires_at=expires_at,
                refresh_token=refresh_jti,
                access_token=access_jti,
            )

            SecurityLog.objects.create(
                user=user,
                event_type="login",
                ip_address=client_ip,
                user_agent=user_agent,
                details="User logged in successfully with 2FA",
            )

            user_data = UserProfileSerializer(user).data
            # Return using Verify2FAResponseSerializer structure
            return Response(
                {
                    "status": True,
                    "user": user_data,
                    "refreshToken": str(refresh),
                    "accessToken": str(access_token),
                    "expiresIn": access_exp,
                    "message": "Login successful with two-factor authentication",
                }
            )
        except Exception as e:
            logger.error(f"Error verifying 2FA: {str(e)}")
            return Response(
                {
                    "status": False,
                    "detail": "Error verifying two-factor authentication",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class Resend2FAOTPView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=Resend2FARequestSerializer,
        responses={
            200: Resend2FAResponseSerializer,
            400: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Resend 2FA OTP request",
                value={"checkpoint_token": "a1b2c3d4-e5f6-7890-1234-567890abcdef"},
                request_only=True,
            ),
            OpenApiExample(
                "Resend 2FA OTP successful",
                value={
                    "status": True,
                    "message": "Verification code has been resent",
                    "expires_in": 300,
                },
                response_only=True,
            ),
        ],
        description="Resend 2FA OTP for an ongoing 2FA login.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = Resend2FARequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        checkpoint_token = serializer.validated_data["checkpoint_token"]

        try:
            checkpoint = LoginCheckpoint.objects.filter(
                token=checkpoint_token, is_used=False, expires_at__gt=timezone.now()
            ).first()

            if not checkpoint:
                return Response(
                    {"status": False, "detail": "Invalid or expired checkpoint token"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = checkpoint.user

            otp_code = f"{random.randint(0, 999999):06d}"
            OtpRequest.objects.create(
                user=user,
                otp_code=otp_code,
                type=OtpRequest.EMAIL,
                email=user.email,
                expires_at=timezone.now() + timedelta(minutes=5),
            )

            logger.info(f"Resent 2FA OTP for {user.email}: {otp_code}")

            # Return using Resend2FAResponseSerializer structure
            return Response(
                {
                    "status": True,
                    "message": "Verification code has been resent",
                    "expires_in": 300,
                }
            )
        except Exception as e:
            logger.error(f"Error resending 2FA OTP: {str(e)}")
            return Response(
                {"status": False, "detail": "Error resending verification code"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )