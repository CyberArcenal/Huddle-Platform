from django.core.exceptions import ObjectDoesNotExist
from typing import Optional
from ..models import UserSecuritySettings, User


class UserSecuritySettingsService:
    """Service for UserSecuritySettings model operations"""
    
    @staticmethod
    def create_default_settings(user: User) -> UserSecuritySettings:
        """Create default security settings for a user"""
        settings = UserSecuritySettings.objects.create(
            user=user,
            two_factor_enabled=False,
            recovery_email=user.email,
            alert_on_new_device=True,
            alert_on_password_change=True,
            alert_on_failed_login=True
        )
        return settings
    
    @staticmethod
    def get_settings(user: User) -> Optional[UserSecuritySettings]:
        """Get security settings for a user"""
        try:
            return UserSecuritySettings.objects.get(user=user)
        except UserSecuritySettings.DoesNotExist:
            return None
    
    @staticmethod
    def get_or_create_settings(user: User) -> UserSecuritySettings:
        """Get or create security settings for a user"""
        try:
            return UserSecuritySettings.objects.get(user=user)
        except UserSecuritySettings.DoesNotExist:
            return UserSecuritySettingsService.create_default_settings(user)
    
    @staticmethod
    def update_settings(
        user: User,
        two_factor_enabled: Optional[bool] = None,
        recovery_email: Optional[str] = None,
        recovery_phone: Optional[str] = None,
        alert_on_new_device: Optional[bool] = None,
        alert_on_password_change: Optional[bool] = None,
        alert_on_failed_login: Optional[bool] = None
    ) -> UserSecuritySettings:
        """Update user security settings"""
        settings = UserSecuritySettingsService.get_or_create_settings(user)
        
        if two_factor_enabled is not None:
            settings.two_factor_enabled = two_factor_enabled
        if recovery_email is not None:
            settings.recovery_email = recovery_email
        if recovery_phone is not None:
            settings.recovery_phone = recovery_phone
        if alert_on_new_device is not None:
            settings.alert_on_new_device = alert_on_new_device
        if alert_on_password_change is not None:
            settings.alert_on_password_change = alert_on_password_change
        if alert_on_failed_login is not None:
            settings.alert_on_failed_login = alert_on_failed_login
        
        settings.save()
        return settings
    
    @staticmethod
    def enable_2fa(user: User) -> UserSecuritySettings:
        """Enable two-factor authentication"""
        return UserSecuritySettingsService.update_settings(
            user, two_factor_enabled=True
        )
    
    @staticmethod
    def disable_2fa(user: User) -> UserSecuritySettings:
        """Disable two-factor authentication"""
        return UserSecuritySettingsService.update_settings(
            user, two_factor_enabled=False
        )
    
    @staticmethod
    def is_2fa_enabled(user: User) -> bool:
        """Check if 2FA is enabled for user"""
        settings = UserSecuritySettingsService.get_settings(user)
        return settings.two_factor_enabled if settings else False