
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404

from ..services.user_activity import UserActivityService
from ..serializers.activity import UserActivitySerializer, ActivitySummarySerializer
from ..models import User, UserActivity


class UserActivityListView(APIView):
    """View for listing user activities"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get activities for current user"""
        try:
            action = request.query_params.get('action')
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))
            
            activities = UserActivityService.get_user_activities(
                user=request.user,
                action=action,
                limit=limit,
                offset=offset
            )
            
            serializer = UserActivitySerializer(
                activities,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'count': len(activities),
                'activities': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class FollowingActivityView(APIView):
    """View for getting activities from followed users"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get activities from users being followed"""
        try:
            limit = int(request.query_params.get('limit', 50))
            
            activities = UserActivityService.get_following_activities(
                user=request.user,
                limit=limit
            )
            
            serializer = UserActivitySerializer(
                activities,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'count': len(activities),
                'activities': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class ActivitySummaryView(APIView):
    """View for getting activity summary/statistics"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get activity summary for current user"""
        try:
            from django.db.models import Count, Q
            from django.utils import timezone
            from datetime import timedelta
            
            # Calculate time thresholds
            now = timezone.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = now - timedelta(days=now.weekday())
            
            # Get total activities
            total_activities = UserActivity.objects.filter(user=request.user).count()
            
            # Get last activity
            last_activity = UserActivity.objects.filter(
                user=request.user
            ).order_by('-timestamp').first()
            
            # Get activities by type
            activities_by_type = UserActivity.objects.filter(
                user=request.user
            ).values('action').annotate(count=Count('id')).order_by('-count')
            
            # Convert to dictionary
            activity_types = {item['action']: item['count'] for item in activities_by_type}
            
            # Get activities today
            activities_today = UserActivity.objects.filter(
                user=request.user,
                timestamp__gte=today_start
            ).count()
            
            # Get activities this week
            activities_this_week = UserActivity.objects.filter(
                user=request.user,
                timestamp__gte=week_start
            ).count()
            
            # Prepare summary data
            summary_data = {
                'total_activities': total_activities,
                'last_activity': last_activity.timestamp if last_activity else None,
                'activities_by_type': activity_types,
                'activities_today': activities_today,
                'activities_this_week': activities_this_week
            }
            
            serializer = ActivitySummarySerializer(summary_data)
            
            return Response({
                'user_id': request.user.id,
                'summary': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class RecentActivitiesView(APIView):
    """View for getting recent activities across all users"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get recent activities (public or from followed users)"""
        try:
            limit = int(request.query_params.get('limit', 100))
            action = request.query_params.get('action')
            user_id = request.query_params.get('user_id')
            
            user = None
            if user_id:
                user = get_object_or_404(User, id=user_id)
            
            activities = UserActivityService.get_recent_activities(
                limit=limit,
                action=action,
                user=user
            )
            
            serializer = UserActivitySerializer(
                activities,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'count': len(activities),
                'activities': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class LogActivityView(APIView):
    """View for logging user activities (for internal use)"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Log a user activity"""
        try:
            # Validate required fields
            action = request.data.get('action')
            description = request.data.get('description', '')
            
            if not action:
                return Response(
                    {'error': 'Action is required'},
                    status=status.HTTP_400_BAD_REQUEST
            )
            
            # Validate action type
            valid_actions = [choice[0] for choice in UserActivityService.ACTION_TYPES]
            if action not in valid_actions:
                return Response(
                    {'error': f'Invalid action. Must be one of: {valid_actions}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log activity
            activity = UserActivityService.log_activity(
                user=request.user,
                action=action,
                description=description,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                location=request.data.get('location'),
                metadata=request.data.get('metadata', {})
            )
            
            serializer = UserActivitySerializer(
                activity,
                context={'request': request}
            )
            
            return Response(
                {
                    'message': 'Activity logged successfully',
                    'activity': serializer.data
                },
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )