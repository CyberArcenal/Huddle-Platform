from tokenize import TokenError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
import logging
from global_utils.security import get_client_ip

from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from users.models.base import BlacklistedAccessToken, LoginSession, SecurityLog, User
from users.serializers.auth import LogoutRequestSerializer, LogoutResponseSerializer
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiTypes
logger = logging.getLogger(__name__)
class LogoutView(APIView):
    """
    Improved logout view with proper token blacklisting (similar to base.py)
    """
    @extend_schema(
        request=LogoutRequestSerializer,
        responses={
            200: LogoutResponseSerializer,
            400: OpenApiTypes.OBJECT,
            401: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                'Logout request',
                value={'refresh': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc0MTU5NjAwMCwianRpIjoiMTIzYWJjIiwidXNlcl9pZCI6MX0...'},
                request_only=True,
            ),
            OpenApiExample(
                'Logout successful',
                value={'status': True, 'message': 'Logged out successfully'},
                response_only=True,
            ),
        ],
        description="Logout the current session by blacklisting tokens."
    )
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        user = request.user

        refresh_token_str = request.data.get("refresh")

        if not refresh_token_str:
            return Response(
                {"status": False, "detail": "Refresh token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh_token = RefreshToken(refresh_token_str)
            user_id = refresh_token["user_id"]
            refresh_jti = refresh_token["jti"]
            access_jti = refresh_token.access_token["jti"]

            try:
                user = User.objects.get(id=user_id)

                # Find the login session
                session = LoginSession.objects.filter(
                    user=user, 
                    refresh_token=refresh_jti,
                    is_active=True
                ).first()

                # BLACKLIST ACCESS TOKEN - IMPORTANT!
                if access_jti:
                    BlacklistedAccessToken.blacklist_token(
                        jti=access_jti,
                        user=user,
                        expires_at=timezone.now() + timezone.timedelta(days=1)
                    )
                    logger.info(f"Blacklisted access token JTI: {access_jti}")

                # Blacklist the refresh token
                try:
                    refresh_token.blacklist()
                except Exception:
                    # Fallback: manually blacklist refresh token
                    try:
                        outstanding = OutstandingToken.objects.get(jti=refresh_jti)
                        BlacklistedToken.objects.get_or_create(token=outstanding)
                    except OutstandingToken.DoesNotExist:
                        pass

                # Mark session as inactive if exists
                if session:
                    session.is_active = False
                    session.expires_at = timezone.now()
                    session.save(update_fields=["is_active", "expires_at"])

                # Cleanup expired blacklisted tokens
                BlacklistedAccessToken.cleanup_expired()

                # Log security event
                SecurityLog.objects.create(
                    user=user,
                    event_type="logout",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    details="User logged out (tokens blacklisted)"
                )

                return Response(
                    {"status": True, "message": "Logged out successfully"},
                    status=status.HTTP_200_OK,
                )

            except User.DoesNotExist:
                logger.warning(f"User not found during logout: {user_id}")
                return Response(
                    {"status": False, "detail": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        except TokenError as e:
            logger.warning(f"Logout failed due to invalid token: {str(e)}")
            return Response(
                {"status": False, "detail": "Invalid refresh token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            logger.error(f"Unexpected error during logout: {str(e)}")
            return Response(
                {"status": False, "detail": "An error occurred during logout"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LogoutAllView(APIView):
    """
    Improved logout all view with proper token blacklisting (similar to base.py)
    """
    @extend_schema(
        responses={
            200: LogoutResponseSerializer,
            401: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                'Logout all successful',
                value={'status': True, 'message': 'Logged out from 2 devices successfully'},
                response_only=True,
            ),
        ],
        description="Logout from all active sessions by blacklisting all tokens."
    )
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        user = request.user

        if not user.is_authenticated:
            return Response(
                {"status": False, "detail": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            # Get all active sessions for the user
            active_sessions = LoginSession.objects.filter(user=user, is_active=True)
            terminated_count = 0

            # Blacklist all tokens and mark sessions inactive
            for session in active_sessions:
                try:
                    # BLACKLIST ACCESS TOKEN
                    if session.access_token:
                        BlacklistedAccessToken.blacklist_token(
                            jti=session.access_token,
                            user=user,
                            expires_at=timezone.now() + timezone.timedelta(days=1)
                        )

                    # Blacklist refresh token
                    try:
                        token = RefreshToken()
                        token["jti"] = session.refresh_token
                        token.blacklist()
                    except Exception:
                        try:
                            outstanding = OutstandingToken.objects.get(jti=session.refresh_token)
                            BlacklistedToken.objects.get_or_create(token=outstanding)
                        except OutstandingToken.DoesNotExist:
                            pass

                    # Mark session inactive
                    session.is_active = False
                    session.expires_at = timezone.now()
                    session.save(update_fields=["is_active", "expires_at"])
                    terminated_count += 1

                except Exception as e:
                    logger.error(f"Failed to terminate session {session.id}: {e}")
                    continue

            # Cleanup expired blacklisted tokens
            BlacklistedAccessToken.cleanup_expired()

            # Log security event
            SecurityLog.objects.create(
                user=user,
                event_type="logout",
                ip_address=client_ip,
                user_agent=user_agent,
                details=f"All sessions terminated ({terminated_count} sessions, tokens blacklisted)"
            )

            return Response(
                {"status": True, "message": f"Logged out from {terminated_count} devices successfully"},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Unexpected error during logout all: {str(e)}")
            return Response(
                {"status": False, "detail": "An error occurred during logout"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )