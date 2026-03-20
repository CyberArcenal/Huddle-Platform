# serializers/admin_serializer.py
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from typing import Dict, Any, List, Optional

from users.serializers.activity import UserActivitySerializer
from users.serializers.base import ActivitySerializer, FollowerSerializer, FollowingSerializer, LoginSessionSerializer, SecurityLogSerializer
from users.serializers.user import UserProfileSerializer
from users.services.user import UserService

from ..models import User, UserStatus, UserActivity, SecurityLog


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """Admin serializer for updating any user (with elevated permissions)"""
    
    status = serializers.ChoiceField(
        choices=[(status.value, status.name) for status in UserStatus],
        required=False
    )
    admin_notes = serializers.CharField(
        required=False,
        write_only=True,
        max_length=500,
        help_text="Internal notes about this change"
    )
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name',
            'date_of_birth', 'phone_number', 'bio',
            'is_verified', 'status', 'is_active', 'admin_notes'
        ]
    
    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate admin update"""
        # Check if admin is trying to modify superuser (add restrictions if needed)
        request = self.context.get('request')
        user_to_update = self.instance
        
        if user_to_update and user_to_update.is_superuser:
            # Prevent non-superusers from modifying superusers
            if not request.user.is_superuser:
                raise serializers.ValidationError(
                    "Only superusers can modify other superusers"
                )
        
        return attrs
    
    @transaction.atomic
    def update(self, instance: User, validated_data: Dict[str, Any]) -> User:
        """Update user with admin permissions"""
        request = self.context.get('request')
        admin_notes = validated_data.pop('admin_notes', None)
        
        # Track changes for audit log
        changes = {}
        for field, new_value in validated_data.items():
            old_value = getattr(instance, field)
            if old_value != new_value:
                changes[field] = {
                    'old': str(old_value),
                    'new': str(new_value)
                }
        
        # Update user
        for field, value in validated_data.items():
            setattr(instance, field, value)
        
        instance.save()
        
        # Log admin activity
        if changes:
            UserActivity.objects.create(
                user=instance,
                action='admin_profile_update',
                description=f"Profile updated by admin {request.user.username}",
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                metadata={
                    'admin_id': request.user.id,
                    'admin_username': request.user.username,
                    'changes': changes,
                    'notes': admin_notes
                }
            )
            
            # Also log in security logs
            SecurityLog.objects.create(
                user=instance,
                event_type='admin_action',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                details=f"Profile modified by admin. Changes: {changes}"
            )
        
        return instance


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """Admin serializer for creating users"""
    
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    send_welcome_email = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Send welcome email to new user"
    )
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'first_name', 'last_name',
            'date_of_birth', 'phone_number', 'bio', 'is_verified',
            'status', 'is_active', 'send_welcome_email'
        ]
    
    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> User:
        """Create user as admin"""
        request = self.context.get('request')
        send_welcome_email = validated_data.pop('send_welcome_email', False)
        password = validated_data.pop('password')
        
        # Create user
        user = UserService.create_user(
            username=validated_data.get('username'),
            email=validated_data.get('email'),
            password=password,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone_number=validated_data.get('phone_number', ''),
            **{k: v for k, v in validated_data.items() 
               if k not in ['username', 'email', 'first_name', 'last_name', 'phone_number']}
        )
        
        # Log admin activity
        UserActivity.objects.create(
            user=user,
            action='admin_created_account',
            description=f"Account created by admin {request.user.username}",
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            metadata={
                'admin_id': request.user.id,
                'admin_username': request.user.username,
                'send_welcome_email': send_welcome_email
            }
        )
        
        # Send welcome email if requested
        if send_welcome_email:
            # Implement email sending logic here
            pass
        
        return user


class AdminUserListSerializer(UserProfileSerializer):
    """Admin serializer for listing users with additional admin info"""
    
    last_login = serializers.DateTimeField(read_only=True)
    login_count = serializers.SerializerMethodField()
    security_logs_count = serializers.SerializerMethodField()
    
    class Meta(UserProfileSerializer.Meta):
        fields = UserProfileSerializer.Meta.fields + [
            'last_login', 'login_count', 'security_logs_count',
            'is_active', 'is_superuser', 'is_staff'
        ]
    
    def get_login_count(self, obj) -> int:
        """Get number of login sessions"""
        return obj.login_sessions.count()
    
    def get_security_logs_count(self, obj) -> int:
        """Get number of security logs"""
        return obj.security_logs.count()


class BulkUserActionSerializer(serializers.Serializer):
    """Serializer for bulk user actions (activate, deactivate, delete)"""
    
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        min_length=1,
        max_length=100  # Limit bulk operations
    )
    action = serializers.ChoiceField(
        required=True,
        choices=[
            ('activate', 'Activate Users'),
            ('deactivate', 'Deactivate Users'),
            ('soft_delete', 'Soft Delete Users'),
            ('hard_delete', 'Hard Delete Users'),
            ('verify', 'Verify Users'),
            ('unverify', 'Unverify Users')
        ]
    )
    reason = serializers.CharField(
        required=False,
        max_length=500,
        help_text="Reason for bulk action"
    )
    
    def validate_user_ids(self, value: List[int]) -> List[int]:
        """Validate user IDs"""
        # Check if all users exist
        existing_count = User.objects.filter(id__in=value).count()
        if existing_count != len(value):
            raise serializers.ValidationError(
                f"Some users not found. Found {existing_count} out of {len(value)}"
            )
        
        # Check permissions for superuser modification
        request = self.context.get('request')
        if request and not request.user.is_superuser:
            superusers = User.objects.filter(id__in=value, is_superuser=True)
            if superusers.exists():
                raise serializers.ValidationError(
                    "Cannot perform bulk actions on superusers without superuser privileges"
                )
        
        return value
    
    @transaction.atomic
    def execute(self) -> Dict[str, Any]:
        """Execute bulk action"""
        request = self.context.get('request')
        user_ids = self.validated_data['user_ids']
        action = self.validated_data['action']
        reason = self.validated_data.get('reason', '')
        
        users = User.objects.filter(id__in=user_ids)
        results = {
            'success': 0,
            'failed': 0,
            'details': []
        }
        
        for user in users:
            try:
                if action == 'activate':
                    user.is_active = True
                    user.status = 'ACTIVE'
                    user.save()
                    status = 'activated'
                    
                elif action == 'deactivate':
                    user = UserService.deactivate_user(user)
                    status = 'deactivated'
                    
                elif action == 'soft_delete':
                    UserService.delete_user(user, soft_delete=True)
                    status = 'soft_deleted'
                    
                elif action == 'hard_delete':
                    UserService.delete_user(user, soft_delete=False)
                    status = 'hard_deleted'
                    
                elif action == 'verify':
                    user.is_verified = True
                    user.save()
                    status = 'verified'
                    
                elif action == 'unverify':
                    user.is_verified = False
                    user.save()
                    status = 'unverified'
                
                # Log admin activity
                UserActivity.objects.create(
                    user=user,
                    action=f'admin_bulk_{action}',
                    description=f"User {status} by admin {request.user.username}",
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT'),
                    metadata={
                        'admin_id': request.user.id,
                        'admin_username': request.user.username,
                        'action': action,
                        'reason': reason
                    }
                )
                
                results['success'] += 1
                results['details'].append({
                    'user_id': user.id,
                    'username': user.username,
                    'status': 'success',
                    'action': action
                })
                
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'user_id': user.id,
                    'username': user.username,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return results


class UserExportSerializer(serializers.ModelSerializer):
    """Serializer for GDPR/data export compliance"""

    followers = serializers.SerializerMethodField()
    following = serializers.SerializerMethodField()
    activities = serializers.SerializerMethodField()
    security_logs = serializers.SerializerMethodField()
    login_sessions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'date_of_birth', 'phone_number', 'bio', 'is_verified',
            'status', 'is_active', 'date_joined', 'last_login',
            'followers', 'following', 'activities',
            'security_logs', 'login_sessions'
        ]

    def get_followers(self, obj) -> FollowerSerializer:
        return FollowerSerializer(obj.followers.values(
            'follower_id', 'follower__username', 'created_at'
        ), many=True).data

    def get_following(self, obj) -> FollowingSerializer:
        return FollowingSerializer(obj.following.values(
            'following_id', 'following__username', 'created_at'
        ), many=True).data

    def get_activities(self, obj) -> ActivitySerializer:
        return ActivitySerializer(obj.activities.values(
            'action', 'description', 'timestamp',
            'ip_address', 'location', 'metadata'
        ), many=True).data

    def get_security_logs(self, obj) -> SecurityLogSerializer:
        return SecurityLogSerializer(obj.security_logs.values(
            'event_type', 'created_at', 'ip_address',
            'user_agent', 'details'
        ), many=True).data

    def get_login_sessions(self, obj) -> LoginSessionSerializer:
        return LoginSessionSerializer(obj.login_sessions.values(
            'device_name', 'ip_address', 'created_at',
            'last_used', 'expires_at', 'is_active'
        ), many=True).data
        
        
        
        
        



# ===== Response serializers for drf-spectacular =====

class AdminUserDetailResponseSerializer(serializers.Serializer):
    user = AdminUserListSerializer()
    recent_activities = UserActivitySerializer(many=True)
    recent_security_logs = SecurityLogSerializer(many=True)


class AdminCreateUserResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = AdminUserListSerializer()


class BulkActionDetailSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    status = serializers.CharField()
    error = serializers.CharField(required=False)
    action = serializers.CharField(required=False)


class BulkActionResultSerializer(serializers.Serializer):
    success = serializers.IntegerField()
    failed = serializers.IntegerField()
    details = BulkActionDetailSerializer(many=True)


class AdminBulkUserActionResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    results = BulkActionResultSerializer()


class DashboardUserStatisticsSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    new_users_today = serializers.IntegerField()
    new_users_week = serializers.IntegerField()
    status_breakdown = serializers.ListField(child=serializers.DictField())


class DashboardActivityStatisticsSerializer(serializers.Serializer):
    total_activities = serializers.IntegerField()
    activities_today = serializers.IntegerField()


class DashboardSecurityStatisticsSerializer(serializers.Serializer):
    failed_logins_24h = serializers.IntegerField()
    password_changes_24h = serializers.IntegerField()


class AdminDashboardResponseSerializer(serializers.Serializer):
    user_statistics = DashboardUserStatisticsSerializer()
    activity_statistics = DashboardActivityStatisticsSerializer()
    security_statistics = DashboardSecurityStatisticsSerializer()
    timestamp = serializers.DateTimeField()


class UserExportResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    export_timestamp = serializers.DateTimeField()
    data = UserExportSerializer()


class CleanupActionResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    count = serializers.IntegerField()