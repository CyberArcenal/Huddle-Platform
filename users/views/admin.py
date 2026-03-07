from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from global_utils.pagination import UsersPagination

from ..serializers.admin import (
    AdminUserUpdateSerializer,
    AdminUserCreateSerializer,
    AdminUserListSerializer,
    BulkUserActionSerializer,
    UserExportSerializer
)
from ..services.user import UserService
from ..services.security_log import SecurityLogService
from ..services.user_activity import UserActivityService
from ..models import User, UserStatus, SecurityLog, UserActivity


class AdminUserListView(APIView):
    """Admin view for listing users with filters"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get(self, request):
        """Get list of users with admin filters"""
        try:
            # Get query parameters (no limit/offset, they are handled by paginator)
            status_filter = request.query_params.get('status')
            is_verified = request.query_params.get('is_verified')
            is_active = request.query_params.get('is_active')
            search = request.query_params.get('search', '').strip()

            # Build queryset
            queryset = User.objects.all()

            # Apply filters
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            if is_verified is not None:
                queryset = queryset.filter(is_verified=is_verified.lower() == 'true')
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == 'true')
            if search:
                queryset = queryset.filter(
                    Q(username__icontains=search) |
                    Q(email__icontains=search) |
                    Q(first_name__icontains=search) |
                    Q(last_name__icontains=search)
                )

            # Order by date_joined descending
            queryset = queryset.order_by('-date_joined')

            # Apply pagination
            paginator = UsersPagination()
            page = paginator.paginate_queryset(queryset, request)
            serializer = AdminUserListSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminUserDetailView(APIView):
    """Admin view for user details"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get(self, request, user_id):
        """Get user details for admin"""
        try:
            user = get_object_or_404(User, id=user_id)
            
            serializer = AdminUserListSerializer(
                user,
                context={'request': request}
            )
            
            # Get additional admin data
            recent_activities = UserActivity.objects.filter(
                user=user
            ).order_by('-timestamp')[:10]
            
            security_logs = SecurityLog.objects.filter(
                user=user
            ).order_by('-created_at')[:10]
            
            from ..serializers.activity import UserActivitySerializer
            from ..serializers.security import SecurityLogSerializer
            
            activity_serializer = UserActivitySerializer(
                recent_activities,
                many=True,
                context={'request': request}
            )
            
            security_serializer = SecurityLogSerializer(
                security_logs,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'user': serializer.data,
                'recent_activities': activity_serializer.data,
                'recent_security_logs': security_serializer.data
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def put(self, request, user_id):
        """Update user as admin"""
        try:
            user = get_object_or_404(User, id=user_id)
            
            serializer = AdminUserUpdateSerializer(
                user,
                data=request.data,
                partial=True,
                context={'request': request}
            )
            
            if serializer.is_valid():
                updated_user = serializer.save()
                
                return Response(
                    {
                        'message': 'User updated successfully',
                        'user': AdminUserListSerializer(
                            updated_user,
                            context={'request': request}
                        ).data
                    }
                )
            
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class AdminCreateUserView(APIView):
    """Admin view for creating users"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def post(self, request):
        """Create user as admin"""
        serializer = AdminUserCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                user = serializer.save()
                
                return Response(
                    {
                        'message': 'User created successfully',
                        'user': AdminUserListSerializer(
                            user,
                            context={'request': request}
                        ).data
                    },
                    status=status.HTTP_201_CREATED
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


class AdminBulkUserActionView(APIView):
    """Admin view for bulk user actions"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def post(self, request):
        """Execute bulk action on users"""
        serializer = BulkUserActionSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                results = serializer.execute()
                
                return Response({
                    'message': f'Bulk action completed: {results["success"]} successful, {results["failed"]} failed',
                    'results': results
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


class AdminDashboardView(APIView):
    """Admin dashboard with statistics"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get(self, request):
        """Get admin dashboard statistics"""
        try:
            # User statistics
            total_users = User.objects.count()
            active_users = User.objects.filter(status=UserStatus.ACTIVE).count()
            new_users_today = User.objects.filter(
                created_at__gte=timezone.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            ).count()
            new_users_week = User.objects.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count()
            
            # User status breakdown
            status_breakdown = User.objects.values('status').annotate(
                count=Count('id')
            ).order_by('-count')
            
            # Activity statistics
            total_activities = UserActivity.objects.count()
            activities_today = UserActivity.objects.filter(
                timestamp__gte=timezone.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            ).count()
            
            # Security statistics
            failed_logins_24h = SecurityLog.objects.filter(
                event_type='failed_login',
                created_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
            
            password_changes_24h = SecurityLog.objects.filter(
                event_type='password_change',
                created_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
            
            return Response({
                'user_statistics': {
                    'total_users': total_users,
                    'active_users': active_users,
                    'new_users_today': new_users_today,
                    'new_users_week': new_users_week,
                    'status_breakdown': list(status_breakdown)
                },
                'activity_statistics': {
                    'total_activities': total_activities,
                    'activities_today': activities_today
                },
                'security_statistics': {
                    'failed_logins_24h': failed_logins_24h,
                    'password_changes_24h': password_changes_24h
                },
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserExportView(APIView):
    """View for exporting user data (GDPR compliance)"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get(self, request, user_id):
        """Export all data for a user"""
        try:
            user = get_object_or_404(User, id=user_id)
            
            serializer = UserExportSerializer(
                user,
                context={'request': request}
            )
            
            return Response({
                'user_id': user_id,
                'export_timestamp': timezone.now(),
                'data': serializer.data
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class AdminCleanupView(APIView):
    """Admin view for cleanup operations"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def post(self, request):
        """Execute cleanup operations"""
        try:
            from ..services.login_session import LoginSessionService
            from ..services.blacklisted_access_token import BlacklistedAccessTokenService
            from ..services.otp_request import OtpRequestService
            from ..services.login_checkpoint import LoginCheckpointService
            
            action = request.data.get('action')
            
            if action == 'cleanup_expired_sessions':
                count = LoginSessionService.cleanup_expired_sessions()
                return Response({
                    'message': f'Cleaned up {count} expired sessions',
                    'count': count
                })
            
            elif action == 'cleanup_expired_tokens':
                count = BlacklistedAccessTokenService.cleanup_expired_tokens()
                return Response({
                    'message': f'Cleaned up {count} expired blacklisted tokens',
                    'count': count
                })
            
            elif action == 'cleanup_expired_otps':
                count = OtpRequestService.cleanup_expired_otps()
                return Response({
                    'message': f'Cleaned up {count} expired OTPs',
                    'count': count
                })
            
            elif action == 'cleanup_expired_checkpoints':
                count = LoginCheckpointService.cleanup_expired_checkpoints()
                return Response({
                    'message': f'Cleaned up {count} expired checkpoints',
                    'count': count
                })
            
            elif action == 'cleanup_old_logs':
                days = int(request.data.get('days', 90))
                count = SecurityLogService.cleanup_old_logs(days)
                return Response({
                    'message': f'Cleaned up {count} logs older than {days} days',
                    'count': count
                })
            
            elif action == 'cleanup_old_activities':
                days = int(request.data.get('days', 365))
                count = UserActivityService.cleanup_old_activities(days)
                return Response({
                    'message': f'Cleaned up {count} activities older than {days} days',
                    'count': count
                })
            
            else:
                return Response(
                    {'error': 'Invalid cleanup action'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )