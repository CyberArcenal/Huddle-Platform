# serializers/activity_serializer.py
from rest_framework import serializers
from django.utils import timezone
from django.db.models import Count, Q
from typing import Dict, Any, List, Optional

from users.serializers.user import UserListSerializer

from ..models import UserActivity, SecurityLog, LoginSession


class UserActivitySerializer(serializers.ModelSerializer):
    """Serializer for user activity logs"""
    
    user = UserListSerializer(read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    formatted_time = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = UserActivity
        fields = [
            'id', 'user', 'action', 'action_display',
            'description', 'ip_address', 'user_agent',
            'timestamp', 'formatted_time', 'time_ago',
            'location', 'metadata'
        ]
        read_only_fields = fields
    
    def get_formatted_time(self, obj) -> str:
        """Format timestamp to readable string"""
        return obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    
    def get_time_ago(self, obj) -> str:
        """Get human-readable time difference"""
        now = timezone.now()
        delta = now - obj.timestamp
        
        if delta.days > 365:
            years = delta.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"


class ActivitySummarySerializer(serializers.Serializer):
    """Serializer for user activity summary/statistics"""
    
    total_activities = serializers.IntegerField()
    last_activity = serializers.DateTimeField()
    activities_by_type = serializers.DictField()
    activities_today = serializers.IntegerField()
    activities_this_week = serializers.IntegerField()
    
    def to_representation(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        """Format activity summary"""
        return {
            'total_activities': instance.get('total_activities', 0),
            'last_activity': instance.get('last_activity'),
            'activity_types': instance.get('activities_by_type', {}),
            'today': instance.get('activities_today', 0),
            'this_week': instance.get('activities_this_week', 0)
        }


class LoginSessionSerializer(serializers.ModelSerializer):
    """Serializer for login sessions"""
    
    device_type = serializers.SerializerMethodField()
    is_current = serializers.SerializerMethodField()
    formatted_last_used = serializers.SerializerMethodField()
    
    class Meta:
        model = LoginSession
        fields = [
            'id', 'device_name', 'device_type',
            'ip_address', 'created_at', 'last_used',
            'formatted_last_used', 'expires_at',
            'is_active', 'is_valid', 'is_current'
        ]
        read_only_fields = fields
    
    def get_device_type(self, obj) -> str:
        """Detect device type from user agent"""
        user_agent = obj.user_agent or ''
        user_agent_lower = user_agent.lower()
        
        if 'mobile' in user_agent_lower or 'android' in user_agent_lower or 'iphone' in user_agent_lower:
            return 'mobile'
        elif 'tablet' in user_agent_lower or 'ipad' in user_agent_lower:
            return 'tablet'
        else:
            return 'desktop'
    
    def get_is_current(self, obj) -> bool:
        """Check if this is the current session"""
        request = self.context.get('request')
        if request and hasattr(request, 'auth'):
            # Compare session ID with current session
            # This depends on your JWT implementation
            return False  # Placeholder - implement based on your auth system
        return False
    
    def get_formatted_last_used(self, obj) -> str:
        """Format last used time"""
        return obj.last_used.strftime('%Y-%m-%d %H:%M:%S')


class TerminateSessionSerializer(serializers.Serializer):
    """Serializer for terminating login sessions"""
    
    session_id = serializers.UUIDField(required=True)
    
    def validate_session_id(self, value) -> str:
        """Validate session ID"""
        request = self.context.get('request')
        
        try:
            session = LoginSession.objects.get(id=value, user=request.user)
            
            # Don't allow terminating current session (if we can identify it)
            if self.context.get('is_current_session', False):
                raise serializers.ValidationError("Cannot terminate current session")
            
            return value
        except LoginSession.DoesNotExist:
            raise serializers.ValidationError("Session not found")
    
    def terminate(self) -> bool:
        """Terminate the session"""
        session_id = self.validated_data['session_id']
        request = self.context.get('request')
        
        try:
            session = LoginSession.objects.get(id=session_id, user=request.user)
            session.is_active = False
            session.save()
            
            # Log activity
            UserActivity.objects.create(
                user=request.user,
                action='session_terminated',
                description=f"Terminated session on {session.device_name}",
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                metadata={'terminated_session_id': str(session_id)}
            )
            
            return True
        except LoginSession.DoesNotExist:
            return False


class BulkTerminateSessionsSerializer(serializers.Serializer):
    """Serializer for terminating multiple login sessions"""
    
    session_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        min_length=1,
        max_length=50  # Limit bulk operations
    )
    terminate_all = serializers.BooleanField(default=False)
    
    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate session IDs"""
        request = self.context.get('request')
        
        if attrs.get('terminate_all'):
            return attrs
        
        # Validate each session belongs to the user
        invalid_sessions = []
        for session_id in attrs['session_ids']:
            if not LoginSession.objects.filter(
                id=session_id,
                user=request.user,
                is_active=True
            ).exists():
                invalid_sessions.append(str(session_id))
        
        if invalid_sessions:
            raise serializers.ValidationError({
                'session_ids': f"Invalid or inactive sessions: {', '.join(invalid_sessions)}"
            })
        
        return attrs
    
    def terminate(self) -> Dict[str, Any]:
        """Terminate multiple sessions"""
        request = self.context.get('request')
        terminate_all = self.validated_data.get('terminate_all', False)
        session_ids = self.validated_data.get('session_ids', [])
        
        if terminate_all:
            # Terminate all sessions except current
            sessions = LoginSession.objects.filter(
                user=request.user,
                is_active=True
            )
            # Filter out current session if identified
            current_session_id = self.context.get('current_session_id')
            if current_session_id:
                sessions = sessions.exclude(id=current_session_id)
            
            terminated_count = sessions.update(is_active=False)
            
            # Log activity
            UserActivity.objects.create(
                user=request.user,
                action='bulk_session_termination',
                description=f"Terminated {terminated_count} sessions",
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
            return {'terminated_count': terminated_count, 'terminated_all': True}
        else:
            # Terminate specific sessions
            sessions = LoginSession.objects.filter(
                id__in=session_ids,
                user=request.user,
                is_active=True
            )
            
            terminated_count = sessions.update(is_active=False)
            
            # Log activity
            UserActivity.objects.create(
                user=request.user,
                action='bulk_session_termination',
                description=f"Terminated {terminated_count} selected sessions",
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                metadata={'session_ids': session_ids}
            )
            
            return {'terminated_count': terminated_count, 'terminated_all': False}
        
        
        
# ===== Response serializers for drf-spectacular =====

class ActivitySummaryResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    summary = ActivitySummarySerializer()


class LogActivityResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    activity = UserActivitySerializer()