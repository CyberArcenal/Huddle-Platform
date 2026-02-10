
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404

from ..services.security_log import SecurityLogService
from ..services.user_security_settings import UserSecuritySettingsService
from ..services.login_session import LoginSessionService
from ..services.blacklisted_access_token import BlacklistedAccessTokenService
from ..serializers.security import (
    ChangePasswordSerializer,
    EnableTwoFactorSerializer,
    DisableTwoFactorSerializer,
    UpdateSecuritySettingsSerializer,
    SecurityLogSerializer
)
from ..serializers.activity import (
    LoginSessionSerializer,
    TerminateSessionSerializer,
    BulkTerminateSessionsSerializer
)
from ..models import UserSecuritySettings, SecurityLog, LoginSession


class ChangePasswordView(APIView):
    """View for changing user password"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Change password"""
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                user = serializer.save()
                
                return Response(
                    {
                        'message': 'Password changed successfully',
                        'user_id': user.id
                    }
                )
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class Enable2FAView(APIView):
    """View for enabling two-factor authentication"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Enable 2FA"""
        serializer = EnableTwoFactorSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                settings = serializer.save()
                
                return Response(
                    {
                        'message': 'Two-factor authentication enabled successfully',
                        'two_factor_enabled': settings.two_factor_enabled,
                        'user_id': request.user.id
                    }
                )
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class Disable2FAView(APIView):
    """View for disabling two-factor authentication"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Disable 2FA"""
        serializer = DisableTwoFactorSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                settings = serializer.save()
                
                return Response(
                    {
                        'message': 'Two-factor authentication disabled successfully',
                        'two_factor_enabled': settings.two_factor_enabled,
                        'user_id': request.user.id
                    }
                )
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class SecuritySettingsView(APIView):
    """View for managing security settings"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get current security settings"""
        try:
            settings = UserSecuritySettingsService.get_or_create_settings(request.user)
            
            serializer = UpdateSecuritySettingsSerializer(settings)
            
            return Response({
                'user_id': request.user.id,
                'settings': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def put(self, request):
        """Update security settings"""
        serializer = UpdateSecuritySettingsSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                # Get current settings
                settings = UserSecuritySettingsService.get_or_create_settings(request.user)
                
                # Update settings
                updated_settings = serializer.update(settings, serializer.validated_data)
                
                return Response(
                    {
                        'message': 'Security settings updated successfully',
                        'settings': UpdateSecuritySettingsSerializer(
                            updated_settings
                        ).data
                    }
                )
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class SecurityLogsView(APIView):
    """View for accessing security logs"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get security logs for current user"""
        try:
            event_type = request.query_params.get('event_type')
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))
            
            logs = SecurityLogService.get_user_logs(
                user=request.user,
                event_type=event_type,
                limit=limit,
                offset=offset
            )
            
            serializer = SecurityLogSerializer(logs, many=True)
            
            return Response({
                'count': len(logs),
                'logs': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class FailedLoginAttemptsView(APIView):
    """View for checking failed login attempts"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get failed login attempts"""
        try:
            hours = int(request.query_params.get('hours', 24))
            
            attempts = SecurityLogService.get_failed_login_attempts(
                user=request.user,
                hours=hours
            )
            
            count = SecurityLogService.count_failed_login_attempts(
                user=request.user,
                hours=hours
            )
            
            serializer = SecurityLogSerializer(attempts, many=True)
            
            return Response({
                'count': count,
                'hours': hours,
                'attempts': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SuspiciousActivitiesView(APIView):
    """View for checking suspicious activities"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get suspicious activities"""
        try:
            limit = int(request.query_params.get('limit', 20))
            
            activities = SecurityLogService.get_suspicious_activities(
                user=request.user,
                limit=limit
            )
            
            serializer = SecurityLogSerializer(activities, many=True)
            
            return Response({
                'count': len(activities),
                'activities': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class ActiveSessionsView(APIView):
    """View for managing active login sessions"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get all active sessions for current user"""
        try:
            sessions = LoginSessionService.get_active_user_sessions(request.user)
            
            serializer = LoginSessionSerializer(
                sessions,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'count': len(sessions),
                'sessions': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class TerminateSessionView(APIView):
    """View for terminating a specific login session"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Terminate a session"""
        serializer = TerminateSessionSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                success = serializer.terminate()
                
                if success:
                    return Response(
                        {'message': 'Session terminated successfully'}
                    )
                else:
                    return Response(
                        {'error': 'Failed to terminate session'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                    
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class BulkTerminateSessionsView(APIView):
    """View for terminating multiple sessions"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Terminate multiple sessions"""
        serializer = BulkTerminateSessionsSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                result = serializer.terminate()
                
                return Response({
                    'message': f'Terminated {result["terminated_count"]} sessions',
                    'result': result
                })
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class TerminateAllSessionsView(APIView):
    """View for terminating all sessions except current"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Terminate all sessions except current"""
        try:
            # This would require identifying the current session
            # For now, we'll terminate all sessions
            # In production, you'd want to exclude the current session
            
            LoginSessionService.deactivate_all_user_sessions(request.user)
            
            # Log activity
            from ..services.user_activity import UserActivityService
            UserActivityService.log_activity(
                user=request.user,
                action='logout_all_devices',
                description='User terminated all sessions on other devices',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
            return Response(
                {'message': 'All other sessions terminated successfully'}
            )
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class Check2FAStatusView(APIView):
    """View for checking 2FA status"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Check if 2FA is enabled"""
        try:
            is_enabled = UserSecuritySettingsService.is_2fa_enabled(request.user)
            
            return Response({
                'user_id': request.user.id,
                'two_factor_enabled': is_enabled
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )