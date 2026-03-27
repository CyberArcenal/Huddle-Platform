from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from users.models import BlacklistedAccessToken

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiTypes
from users.serializers.auth import (
    TokenVerifyRequestSerializer,
    TokenVerifyResponseSerializer,
)
from users.serializers.user.minimal import UserMinimalSerializer

User = get_user_model()


class TokenVerifyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Token"],
        
        request=TokenVerifyRequestSerializer,
        responses={
            200: TokenVerifyResponseSerializer,
            400: OpenApiTypes.OBJECT,
            401: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Verify token request",
                value={
                    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzQxNTk2MDAwLCJqdGkiOiIxMjNhYmMiLCJ1c2VyX2lkIjoxfQ..."
                },
                request_only=True,
            ),
            OpenApiExample(
                "Verify token successful",
                value={
                    "valid": True,
                    "detail": "message for validation",
                    "user": {
                        "id": 1,
                        "username": "johndoe",
                        "profile_picture_url": "https://example.com/media/profile_pics/john.jpg",
                        "full_name": "John Doe",
                    },
                },
                response_only=True,
            ),
        ],
        description="Verify if an access token is valid and not blacklisted, and return user info.",
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        # Validate request data using serializer
        serializer = TokenVerifyRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"valid": False, "detail": "invalid data"}, status=status.HTTP_400_BAD_REQUEST)

        token_str = serializer.validated_data["token"]

        try:
            # Validate ang token - signature at expiry
            token = AccessToken(token_str)

            if token.get("token_type") != "access":
                return Response(
                    {"valid": False,"detail": "Only access tokens are allowed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check 1: Kung expired na
            if token.get("exp") < timezone.now().timestamp():
                return Response(
                    {"valid": False,"detail": "Token has expired"}, status=status.HTTP_401_UNAUTHORIZED
                )

            # Check 2: Custom access token blacklist
            jti = token.get("jti")
            if BlacklistedAccessToken.is_blacklisted(jti):
                return Response(
                    {"valid": False, "detail": "Token has been revoked"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # User validation
            user_id = token.get("user_id")
            try:
                user = User.objects.get(id=user_id, is_active=True)
            except User.DoesNotExist:
                return Response(
                    {"valid": False, "detail": "User not found or inactive"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            return Response(
                {
                    "valid": True,
                    "user": UserMinimalSerializer(
                        user, context={"request": request}
                    ).data,
                },
                status=status.HTTP_200_OK,
            )

        except (InvalidToken, TokenError) as e:
            return Response(
                {"valid": False, "detail": "Invalid or expired token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
