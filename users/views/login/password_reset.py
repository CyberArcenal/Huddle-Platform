# accounts/views/password_change.py
import logging
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
from global_utils.response import CustomPagination
from global_utils.security import get_client_ip
from users.models.base import SecurityLog, UserSecuritySettings
from users.utils.authentications import IsAuthenticatedAndNotBlacklisted
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiTypes
from users.serializers.auth import (
    PasswordChangeRequestSerializer,
    PasswordChangeResponseSerializer,
    PasswordHistoryResponseSerializer,
    PasswordStrengthCheckRequestSerializer,
    PasswordStrengthCheckResponseSerializer,
)
logger = logging.getLogger(__name__)

class PasswordChangeView(APIView):
    """
    Change password for authenticated users
    """
    permission_classes = [IsAuthenticatedAndNotBlacklisted]
    @extend_schema(
        request=PasswordChangeRequestSerializer,
        responses={
            200: PasswordChangeResponseSerializer,
            400: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                'Password change request',
                value={
                    'current_password': 'OldPass123!',
                    'new_password': 'NewPass123!',
                    'confirm_password': 'NewPass123!'
                },
                request_only=True,
            ),
            OpenApiExample(
                'Password change successful',
                value={'message': 'Password changed successfully', 'changed_at': '2025-03-08T12:34:56Z'},
                response_only=True,
            ),
        ],
        description="Change the authenticated user's password."
    )
    @transaction.atomic
    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        # Validate required fields
        if not all([current_password, new_password, confirm_password]):
            return Response(
                {"detail": "Current password, new password and confirmation are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if passwords match
        if new_password != confirm_password:
            return Response(
                {"detail": "New passwords do not match"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if new password is different from current password
        if current_password == new_password:
            return Response(
                {"detail": "New password must be different from current password"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user

        # Verify current password
        if not check_password(current_password, user.password):


            # Create security log for failed password change
            SecurityLog.objects.create(
                user=user,
                event_type="password_change_failed",
                ip_address=client_ip,
                user_agent=user_agent,
                details="Incorrect current password provided"
            )

            return Response(
                {"detail": "Current password is incorrect"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate password strength
        password_errors = self._validate_password_strength(new_password)
        if password_errors:
            return Response(
                {"detail": "Password does not meet requirements", "errors": password_errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Update password
            old_password_hash = user.password  # For audit purposes
            user.password = make_password(new_password)
            user.save()


            # Create security log for successful password change
            SecurityLog.objects.create(
                user=user,
                event_type="password_changed",
                ip_address=client_ip,
                user_agent=user_agent,
                details="Password changed successfully"
            )

            # Invalidate all existing sessions except current one if needed
            # This is optional but recommended for security
            if UserSecuritySettings.objects.get(user=user).alert_on_password_change:
                # NotificationService.send_password_changed(user)
                pass
                
            self._invalidate_other_sessions(user, request.session.session_key)

            return Response({
                "message": "Password changed successfully",
                "changed_at": timezone.now().isoformat()
            }, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error(f"Password change failed for user {user.id}: {exc}")


            return Response(
                {"detail": "An error occurred while changing password"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _validate_password_strength(self, password):
        """
        Validate password strength
        """
        errors = []

        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")

        if not any(char.isdigit() for char in password):
            errors.append("Password must contain at least one number")

        if not any(char.isupper() for char in password):
            errors.append("Password must contain at least one uppercase letter")

        if not any(char.islower() for char in password):
            errors.append("Password must contain at least one lowercase letter")

        if not any(char in '!@#$%^&*()_+-=[]{}|;:,.<>?`~' for char in password):
            errors.append("Password must contain at least one special character")

        # Check for common passwords (basic check)
        common_passwords = ['password', '12345678', 'qwerty', 'admin', 'letmein']
        if password.lower() in common_passwords:
            errors.append("Password is too common")

        return errors

    def _invalidate_other_sessions(self, user, current_session_key):
        """
        Invalidate all other sessions except the current one
        This is optional but enhances security
        """
        try:
            from django.contrib.sessions.models import Session
            from django.contrib.auth import SESSION_KEY
            
            # Get all sessions for this user except current one
            sessions = Session.objects.filter(
                expire_date__gte=timezone.now()
            ).exclude(session_key=current_session_key)
            
            for session in sessions:
                session_data = session.get_decoded()
                if session_data.get(SESSION_KEY) == str(user.id):
                    session.delete()
                    
        except Exception as e:
            logger.warning(f"Could not invalidate other sessions: {e}")


class PasswordStrengthCheckView(APIView):
    """
    Check password strength without changing password
    """
    permission_classes = [IsAuthenticatedAndNotBlacklisted]
    @extend_schema(
        request=PasswordStrengthCheckRequestSerializer,
        responses={200: PasswordStrengthCheckResponseSerializer},
        examples=[
            OpenApiExample(
                'Password strength check request',
                value={'password': 'mypassword'},
                request_only=True,
            ),
            OpenApiExample(
                'Password strength check response',
                value={
                    'strength_score': 45,
                    'strength_level': 'fair',
                    'is_acceptable': False,
                    'errors': ['Password must contain at least one number'],
                    'suggestions': ['Add special characters', 'Mix letters, numbers and special characters'],
                },
                response_only=True,
            ),
        ],
        description="Check the strength of a password without changing it."
    )
    def post(self, request):
        password = request.data.get('password', '')

        if not password:
            return Response(
                {"detail": "Password is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        errors = self._validate_password_strength(password)
        strength_score = self._calculate_password_strength(password)

        return Response({
            "strength_score": strength_score,
            "strength_level": self._get_strength_level(strength_score),
            "is_acceptable": len(errors) == 0,
            "errors": errors,
            "suggestions": self._get_password_suggestions(password)
        })

    def _validate_password_strength(self, password):
        """Same validation as PasswordChangeView"""
        errors = []

        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")

        if not any(char.isdigit() for char in password):
            errors.append("Password must contain at least one number")

        if not any(char.isupper() for char in password):
            errors.append("Password must contain at least one uppercase letter")

        if not any(char.islower() for char in password):
            errors.append("Password must contain at least one lowercase letter")

        if not any(char in '!@#$%^&*()_+-=[]{}|;:,.<>?`~' for char in password):
            errors.append("Password must contain at least one special character")

        return errors

    def _calculate_password_strength(self, password):
        """Calculate password strength score (0-100)"""
        score = 0
        
        # Length
        score += min(len(password) * 4, 40)  # Max 40 points for length
        
        # Character variety
        if any(char.isdigit() for char in password):
            score += 10
        if any(char.isupper() for char in password):
            score += 10
        if any(char.islower() for char in password):
            score += 10
        if any(char in '!@#$%^&*()_+-=[]{}|;:,.<>?`~' for char in password):
            score += 20
            
        # Deductions for common patterns
        common_patterns = ['123', 'abc', 'qwe', 'password', 'admin']
        for pattern in common_patterns:
            if pattern in password.lower():
                score -= 15
                
        return max(0, min(100, score))

    def _get_strength_level(self, score):
        if score >= 80:
            return "strong"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "fair"
        else:
            return "weak"

    def _get_password_suggestions(self, password):
        suggestions = []
        
        if len(password) < 12:
            suggestions.append("Use at least 12 characters for better security")
            
        if not any(char in '!@#$%^&*()_+-=[]{}|;:,.<>?`~' for char in password):
            suggestions.append("Add special characters")
            
        if password.isalnum():
            suggestions.append("Mix letters, numbers and special characters")
            
        # Check for sequential characters
        if any(password[i:i+3].isdigit() and 
               int(password[i:i+3]) in range(100, 1000) and 
               int(password[i:i+3]) % 111 == 0 for i in range(len(password)-2)):
            suggestions.append("Avoid sequential numbers (e.g., 123, 456)")
            
        return suggestions


class PasswordHistoryView(APIView):
    """
    Get user's password change history
    """
    permission_classes = [IsAuthenticatedAndNotBlacklisted]
    pagination_class = CustomPagination
    @extend_schema(
        responses={200: PasswordHistoryResponseSerializer},
        examples=[
            OpenApiExample(
                'Password history response',
                value={
                    'total_events': 2,
                    'events': [
                        {
                            'event_type': 'password_changed',
                            'created_at': '2025-03-07T10:00:00Z',
                            'ip_address': '192.168.1.100',
                            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                            'success': True,
                        },
                        {
                            'event_type': 'password_change_failed',
                            'created_at': '2025-03-06T15:30:00Z',
                            'ip_address': '192.168.1.101',
                            'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)',
                            'success': False,
                        },
                    ],
                },
                response_only=True,
            ),
        ],
        description="Get the user's password change history."
    )
    def get(self, request):
        user = request.user
        
        # Get password change events from security logs
        password_events = SecurityLog.objects.filter(
            user=user,
            event_type__in=['password_changed', 'password_change_failed']
        ).order_by('-created_at')

        paginated_events = self.pagination_class().paginate_queryset(password_events, request)
        events_data = []
        for event in paginated_events:
            events_data.append({
                "event_type": event.event_type,
                "created_at": event.created_at.isoformat(),
                "ip_address": event.ip_address,
                "user_agent": event.user_agent,
                "success": event.event_type == 'password_changed'
            })

        return Response({
            "total_events": len(events_data),
            "events": events_data
        })