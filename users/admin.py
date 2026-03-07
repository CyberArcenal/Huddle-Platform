# users/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User,
    UserFollow,
    BlacklistedAccessToken,
    SecurityLog,
    UserSecuritySettings,
    LoginSession,
    LoginCheckpoint,
    OtpRequest,
    UserActivity,
)


class CustomUserAdmin(BaseUserAdmin):
    list_display = (
        "id",
        "username",
        "email",
        "status",
        "is_verified",
        "is_staff",
        "date_joined",
    )
    list_filter = ("status", "is_verified", "is_staff", "is_active", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Profile Info",
            {
                "fields": (
                    "bio",
                    "profile_picture",
                    "cover_photo",
                    "date_of_birth",
                    "phone_number",
                )
            },
        ),
        ("Account Status", {"fields": ("status", "is_verified")}),
    )


@admin.register(UserFollow)
class UserFollowAdmin(admin.ModelAdmin):
    list_display = ("id", "follower", "following", "created_at")
    list_filter = ("created_at",)
    search_fields = ("follower__username", "following__username")
    raw_id_fields = ("follower", "following")
    date_hierarchy = "created_at"


@admin.register(BlacklistedAccessToken)
class BlacklistedAccessTokenAdmin(admin.ModelAdmin):
    list_display = ("jti", "user", "expires_at", "created_at")
    list_filter = ("expires_at", "created_at")
    search_fields = ("jti", "user__username")
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"


@admin.register(SecurityLog)
class SecurityLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "event_type", "ip_address", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("user__username", "ip_address", "details")
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserSecuritySettings)
class UserSecuritySettingsAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "two_factor_enabled",
        "alert_on_new_device",
        "alert_on_password_change",
        "alert_on_failed_login",
    )
    list_filter = (
        "two_factor_enabled",
        "alert_on_new_device",
        "alert_on_password_change",
        "alert_on_failed_login",
    )
    search_fields = ("user__username",)
    raw_id_fields = ("user",)


@admin.register(LoginSession)
class LoginSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "device_name",
        "ip_address",
        "is_active",
        "last_used",
        "expires_at",
    )
    list_filter = ("is_active", "created_at", "last_used")
    search_fields = ("user__username", "device_name", "ip_address")
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"
    readonly_fields = ("id", "created_at", "last_used")


@admin.register(LoginCheckpoint)
class LoginCheckpointAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "email",
        "token_short",
        "is_used",
        "expires_at",
        "created_at",
    )
    list_filter = ("is_used", "expires_at", "created_at")
    search_fields = ("user__username", "email", "token")
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"
    readonly_fields = ("token",)

    def token_short(self, obj):
        return obj.token[:8] + "..." if obj.token else ""

    token_short.short_description = "Token"


@admin.register(OtpRequest)
class OtpRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "type",
        "email",
        "phone",
        "otp_code",
        "is_used",
        "attempt_count",
        "expires_at",
        "created_at",
    )
    list_filter = ("type", "is_used", "created_at")
    search_fields = ("user__username", "email", "phone", "otp_code")
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"
    readonly_fields = ("otp_code",)


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "action", "ip_address", "timestamp", "location")
    list_filter = ("action", "timestamp")
    search_fields = ("user__username", "ip_address", "description")
    raw_id_fields = ("user",)
    date_hierarchy = "timestamp"
    readonly_fields = ("timestamp",)


# Register the custom User model
admin.site.register(User, CustomUserAdmin)
