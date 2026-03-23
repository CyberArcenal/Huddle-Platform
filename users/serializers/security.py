# serializers/security_serializer.py
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from typing import Dict, Any, Optional

from ..models import User, UserSecuritySettings, SecurityLog, UserActivity
from ..services import UserService


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing password"""
    
    current_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Password must be at least 8 characters long"
    )
    confirm_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )
    
    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate password change data"""
        # Check if new passwords match
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'New passwords do not match'
            })
        
        # Check if new password is same as current
        if attrs['current_password'] == attrs['new_password']:
            raise serializers.ValidationError({
                'new_password': 'New password must be different from current password'
            })
        
        # Validate new password strength
        try:
            validate_password(attrs['new_password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({
                'new_password': list(e.messages)
            })
        
        return attrs
    
    def validate_current_password(self, value: str) -> str:
        """Verify current password"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if not request.user.check_password(value):
                raise serializers.ValidationError('Current password is incorrect')
        return value
    
    @transaction.atomic
    def save(self, **kwargs) -> User:
        """Update password"""
        request = self.context.get('request')
        user = request.user
        
        # Update password
        update_data = {'password': self.validated_data['new_password']}
        updated_user = UserService.update_user(user, update_data)
        
        # Log security event
        SecurityLog.objects.create(
            user=user,
            event_type='password_change',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            details='Password changed successfully'
        )
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            action='password_change',
            description='User changed password',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        
        return updated_user


class EnableTwoFactorSerializer(serializers.Serializer):
    """Serializer for enabling two-factor authentication"""
    
    otp_code = serializers.CharField(
        required=True,
        max_length=6,
        min_length=6,
        help_text="6-digit OTP code"
    )
    
    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate OTP code"""
        # In production, implement actual OTP validation
        # This is a placeholder
        request = self.context.get('request')
        otp_code = attrs.get('otp_code')
        
        # Mock validation - replace with real OTP service
        if len(otp_code) != 6 or not otp_code.isdigit():
            raise serializers.ValidationError({
                'otp_code': 'Invalid OTP code format'
            })
        
        return attrs
    
    def save(self, **kwargs) -> UserSecuritySettings:
        """Enable 2FA"""
        request = self.context.get('request')
        user = request.user
        
        # Get or create security settings
        security_settings, created = UserSecuritySettings.objects.get_or_create(
            user=user,
            defaults={'two_factor_enabled': True}
        )
        
        # Enable 2FA
        security_settings.two_factor_enabled = True
        security_settings.save()
        
        # Log security event
        SecurityLog.objects.create(
            user=user,
            event_type='2fa_enabled',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            details='Two-factor authentication enabled'
        )
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            action='2fa_enabled',
            description='User enabled two-factor authentication',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        
        return security_settings


class DisableTwoFactorSerializer(serializers.Serializer):
    """Serializer for disabling two-factor authentication"""
    
    current_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )
    
    def validate_current_password(self, value: str) -> str:
        """Verify current password"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if not request.user.check_password(value):
                raise serializers.ValidationError('Password is incorrect')
        return value
    
    def save(self, **kwargs) -> UserSecuritySettings:
        """Disable 2FA"""
        request = self.context.get('request')
        user = request.user
        
        try:
            security_settings = UserSecuritySettings.objects.get(user=user)
            security_settings.two_factor_enabled = False
            security_settings.save()
            
            # Log security event
            SecurityLog.objects.create(
                user=user,
                event_type='2fa_disabled',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                details='Two-factor authentication disabled'
            )
            
            # Log activity
            UserActivity.objects.create(
                user=user,
                action='2fa_disabled',
                description='User disabled two-factor authentication',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
            return security_settings
            
        except UserSecuritySettings.DoesNotExist:
            # Create settings if they don't exist
            return UserSecuritySettings.objects.create(user=user, two_factor_enabled=False)


class UpdateSecuritySettingsSerializer(serializers.ModelSerializer):
    """Serializer for updating security settings"""
    
    class Meta:
        model = UserSecuritySettings
        fields = [
            'recovery_email', 'recovery_phone',
            'alert_on_new_device', 'alert_on_password_change',
            'alert_on_failed_login'
        ]
    
    def validate_recovery_email(self, value: Optional[str]) -> Optional[str]:
        """Validate recovery email"""
        if value:
            request = self.context.get('request')
            user = request.user if request else None
            
            # Check if recovery email is same as primary
            if user and value.lower() == user.email.lower():
                raise serializers.ValidationError(
                    "Recovery email must be different from primary email"
                )
            
            # Check if email already used by another account
            if User.objects.filter(email__iexact=value).exclude(id=user.id).exists():
                raise serializers.ValidationError(
                    "Recovery email is already registered to another account"
                )
        
        return value.lower() if value else None
    
    def validate_recovery_phone(self, value: Optional[str]) -> Optional[str]:
        """Validate recovery phone number"""
        if value:
            # Basic phone number validation
            if not value.replace('+', '').replace(' ', '').isdigit():
                raise serializers.ValidationError(
                    "Phone number must contain only digits, spaces, and plus sign"
                )
            
            if len(value) < 10 or len(value) > 20:
                raise serializers.ValidationError(
                    "Phone number must be between 10 and 20 characters"
                )
        
        return value
    
    def update(self, instance: UserSecuritySettings, validated_data: Dict[str, Any]) -> UserSecuritySettings:
        """Update security settings"""
        request = self.context.get('request')
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        # Log activity
        if request:
            UserActivity.objects.create(
                user=instance.user,
                action='security_settings_update',
                description='User updated security settings',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                metadata={'updated_fields': list(validated_data.keys())}
            )
        
        return instance


class SecurityLogSerializer(serializers.ModelSerializer):
    """Serializer for security logs"""
    
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    formatted_time = serializers.SerializerMethodField()
    
    class Meta:
        model = SecurityLog
        fields = [
            'id', 'event_type', 'event_type_display',
            'ip_address', 'user_agent', 'created_at',
            'formatted_time', 'details'
        ]
        read_only_fields = fields
    
    def get_formatted_time(self, obj) -> str:
        """Format timestamp for display"""
        return obj.created_at.strftime('%Y-%m-%d %H:%M:%S')
    

class UserSecuritySettingsSerializer(serializers.ModelSerializer):
    """Serializer for user security settings"""
    class Meta:
        model = UserSecuritySettings
        fields = [
            "two_factor_enabled",
            "recovery_email",
            "recovery_phone",
            "alert_on_new_device",
            "alert_on_password_change",
            "alert_on_failed_login",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_recovery_email(self, value: str) -> Optional[str]:
        """Validate recovery email"""
        if value:
            # Check if recovery email is different from primary email
            user = self.context.get("user")
            if user and value.lower() == user.email.lower():
                raise serializers.ValidationError(
                    "Recovery email must be different from primary email"
                )

            # Check if recovery email belongs to another user
            if User.objects.filter(email__iexact=value).exists():
                raise serializers.ValidationError(
                    "Recovery email is already registered to another account"
                )

        return value.lower() if value else None
    




# ===== Response serializers for drf-spectacular =====

class ChangePasswordResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user_id = serializers.IntegerField()


class Enable2FAResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    two_factor_enabled = serializers.BooleanField()
    user_id = serializers.IntegerField()


class Disable2FAResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    two_factor_enabled = serializers.BooleanField()
    user_id = serializers.IntegerField()


class SecuritySettingsGetResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    settings = UpdateSecuritySettingsSerializer()


class SecuritySettingsUpdateResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    settings = UpdateSecuritySettingsSerializer()


class FailedLoginAttemptsResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    hours = serializers.IntegerField()
    attempts = SecurityLogSerializer(many=True)


class SuspiciousActivitiesResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    activities = SecurityLogSerializer(many=True)


class TerminateSessionResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class BulkTerminateSessionsResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    result = serializers.DictField()  # flexible dict for termination results


class TerminateAllSessionsResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class Check2FAStatusResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    two_factor_enabled = serializers.BooleanField()