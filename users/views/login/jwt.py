# accounts/views/refresh_token.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.utils import timezone
from rest_framework.permissions import AllowAny
import logging
from global_utils.security import get_client_ip
import uuid
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiTypes
from users.serializers.auth import (
    TokenRefreshRequestSerializer,
    TokenRefreshResponseSerializer,
)
from users.models.base import LoginSession, User

logger = logging.getLogger(__name__)

class RefreshTokenView(APIView):
    permission_classes = [AllowAny]
    """
    Custom view for refreshing JWT tokens.
    Handles token refresh and updates LoginSession records.
    """
    @extend_schema(
        request=TokenRefreshRequestSerializer,
        responses={
            200: TokenRefreshResponseSerializer,
            400: OpenApiTypes.OBJECT,
            401: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                'Refresh token request',
                value={'refresh': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc0MTU5NjAwMCwianRpIjoiMTIzYWJjIiwidXNlcl9pZCI6MX0...'},
                request_only=True,
            ),
            OpenApiExample(
                'Refresh token successful',
                value={
                    'refresh': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc0MTU5NjAwMCwianRpIjoiNDU2ZGVmIiwidXNlcl9pZCI6MX0...',
                    'access': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzQxNTk2MDAwLCJqdGkiOiI3ODlnaGkiLCJ1c2VyX2lkIjoxfQ...',
                    'message': 'Tokens refreshed successfully',
                },
                response_only=True,
            ),
        ],
        description="Obtain a new access token using a refresh token. Also updates the refresh token (rotation)."
    )
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        device_name = user_agent[:100]  # Truncate to fit max_length=100
        
        refresh_token_str = request.data.get('refresh')
        
        if not refresh_token_str:
            return Response(
                {"detail": "Refresh token is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify and refresh the token
            refresh_token = RefreshToken(refresh_token_str)
            user_id = refresh_token['user_id']
            
            try:
                user = User.objects.get(id=user_id)
                
                # Get the old JTI before refreshing
                old_refresh_jti = refresh_token['jti']
                
                # Refresh the token (this creates a new refresh token)
                new_refresh_token = RefreshToken.for_user(user)
                new_access_token = new_refresh_token.access_token
                
                # Get new JTIs
                new_refresh_jti = new_refresh_token['jti']
                new_access_jti = new_access_token['jti']
                
                # Calculate new expiration
                from django.conf import settings
                refresh_lifetime = settings.SIMPLE_JWT.get('REFRESH_TOKEN_LIFETIME', timezone.timedelta(days=7))
                new_expires_at = timezone.now() + refresh_lifetime
                
                # Update LoginSession or create new one
                try:
                    # Try to find existing session with the old refresh token
                    login_session = LoginSession.objects.get(refresh_token=old_refresh_jti)
                    login_session.refresh_token = new_refresh_jti
                    login_session.access_token = new_access_jti
                    login_session.expires_at = new_expires_at
                    login_session.last_used = timezone.now()
                    login_session.save()
                except LoginSession.DoesNotExist:
                    # Create new session if not found
                    LoginSession.objects.create(
                        id=uuid.uuid4(),
                        user=user,
                        device_name=device_name,
                        ip_address=client_ip,
                        expires_at=new_expires_at,
                        refresh_token=new_refresh_jti,
                        access_token=new_access_jti
                    )
                return Response({
                    "refresh": str(new_refresh_token),
                    "access": str(new_access_token),
                    "message": "Tokens refreshed successfully"
                }, status=status.HTTP_200_OK)
                
            except User.DoesNotExist:
                logger.error(f"User not found during token refresh: {user_id}")
                return Response(
                    {"detail": "User not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
        except TokenError as e:
            logger.warning(f"Token refresh failed: {str(e)}")
            return Response(
                {"detail": "Invalid or expired refresh token"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {str(e)}")
            
            return Response(
                {"detail": "An error occurred during token refresh"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )





