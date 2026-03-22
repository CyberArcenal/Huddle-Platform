from enum import Enum
import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models

from users.enums import UserStatus

ACTION_TYPES = [
    ("login", "Login"),
    ("logout", "Logout"),
    ("update_profile", "Update Profile"),
    ("create_post", "Create Post"),
    ("like_post", "Like Post"),
    ("comment", "Comment"),
    ("follow", "Follow"),
    ("unfollow", "Unfollow"),
    ("join_group", "Join Group"),
    ("leave_group", "Leave Group"),
    ("admin_created_account", "Admin Created Account"),
    ("admin_profile_update", "Admin Profile Update"),
    ("admin_bulk_activate", "Admin Bulk Activate"),
    ("admin_bulk_deactivate", "Admin Bulk Deactivate"),
    ("admin_bulk_soft_delete", "Admin Bulk Soft Delete"),
    ("admin_bulk_hard_delete", "Admin Bulk Hard Delete"),
    ("admin_bulk_verify", "Admin Bulk Verify"),
    ("admin_bulk_unverify", "Admin Bulk Unverify"),
    # Session actions
    ("bulk_session_termination", "Bulk Session Termination"),
    ("session_terminated", "Session Terminated"),
    # User actions
    ("account_created", "Account Created"),
    ("follow_user", "Follow User"),
    ("unfollow_user", "Unfollow User"),
    ("profile_picture_update", "Profile Picture Update"),
    ("profile_picture_removed", "Profile Picture Removed"),
    ("cover_photo_update", "Cover Photo Update"),
    ("cover_photo_removed", "Cover Photo Removed"),
    ("password_change", "Password Change"),
    ("status_change", "Status Change"),  # bagong dagdag
    # Security actions
    ("2fa_enabled", "Two-Factor Authentication Enabled"),
    ("2fa_disabled", "Two-Factor Authentication Disabled"),
    ("security_settings_update", "Security Settings Update"),
]


class OtpRequestStatus(str, Enum):
    USED = "used"
    EXPIRED = "expired"


class OtpRequestTypes(str, Enum):
    EMAIL = "email"
    PHONE = "phone"

OTP_TYPES = [
        ("email", "Email"),
        ("phone", "Phone"),
    ]


USER_STATUS_CHOICES = (
    ("active", "Active"),
    ("restricted", "Restricted"),
    ("suspended", "Suspended"),
    ("deleted", "Deleted"),
)

SECURITY_EVENT_TYPES = [
    ("login", "Login"),
    ("logout", "Logout"),
    ("password_change", "Password Change"),
    ("2fa_enabled", "2FA Enabled"),
    ("2fa_disabled", "2FA Disabled"),
    ("failed_login", "Failed Login"),
]
























