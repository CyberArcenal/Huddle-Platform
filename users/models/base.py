import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models

from users.enums import UserStatus


class User(AbstractUser):
    STATUS_CHOICES = (
        (UserStatus.ACTIVE, "Active"),
        (UserStatus.RESTRICTED, "Restricted"),
        (UserStatus.SUSPENDED, "Suspended"),
        (UserStatus.DELETED, "Deleted"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=UserStatus.ACTIVE,
        help_text="Account status",
    )
    bio = models.TextField(max_length=500, blank=True)
    profile_picture = models.ImageField(
        upload_to="profile_pics/", blank=True, null=True
    )
    cover_photo = models.ImageField(upload_to="covers/", blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"


class UserFollow(models.Model):
    follower = models.ForeignKey(
        User, related_name="following", on_delete=models.CASCADE
    )
    following = models.ForeignKey(
        User, related_name="followers", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("follower", "following")
        db_table = "user_follows"


class BlacklistedAccessToken(models.Model):
    jti = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "blacklisted_access_tokens"

    def __str__(self):
        return f"Blacklisted token {self.jti} for {self.user}"

    @classmethod
    def is_blacklisted(cls, jti):
        """Check if a token jti is blacklisted"""
        return cls.objects.filter(jti=jti).exists()

    @classmethod
    def blacklist_token(cls, jti, user, expires_at):
        """Add a token to blacklist"""
        return cls.objects.get_or_create(
            jti=jti, defaults={"user": user, "expires_at": expires_at}
        )

    @classmethod
    def cleanup_expired(cls):
        """Remove expired blacklisted tokens"""
        cls.objects.filter(expires_at__lt=timezone.now()).delete()


class SecurityLog(models.Model):
    EVENT_TYPES = [
        ("login", "Login"),
        ("logout", "Logout"),
        ("password_change", "Password Change"),
        ("2fa_enabled", "2FA Enabled"),
        ("2fa_disabled", "2FA Disabled"),
        ("failed_login", "Failed Login"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="security_logs"
    )

    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    details = models.TextField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)

    def delete(self, using=None, keep_parents=False):
        """Soft delete instead of hard delete"""
        self.is_deleted = True
        self.save()

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.event_type} @ {self.created_at}"


class UserSecuritySettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="security_settings",
    )
    two_factor_enabled = models.BooleanField(default=False)
    recovery_email = models.EmailField(blank=True, null=True)
    recovery_phone = models.CharField(max_length=20, blank=True, null=True)
    alert_on_new_device = models.BooleanField(default=True)
    alert_on_password_change = models.BooleanField(default=True)
    alert_on_failed_login = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    is_deleted = models.BooleanField(default=False)

    def delete(self, using=None, keep_parents=False):
        """Soft delete instead of hard delete"""
        self.is_deleted = True
        self.save()

    def __str__(self):
        return f"Security settings for {self.user.username}"


class LoginSession(models.Model):
    """Tracks user login sessions for JWT tokens"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_sessions",
    )
    device_name = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    refresh_token = models.CharField(
        max_length=255, unique=True
    )  # Store refresh token jti
    access_token = models.CharField(
        max_length=255, blank=True
    )  # Store access token jti

    class Meta:
        verbose_name = "Login Session"
        verbose_name_plural = "Login Sessions"
        ordering = ["-last_used"]
        indexes = [
            models.Index(fields=["user", "last_used"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.device_name}"

    @property
    def is_valid(self):
        return self.is_active and timezone.now() < self.expires_at


class LoginCheckpoint(models.Model):
    """Secure checkpoint for 2FA login or registration flow"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,  # allow None for pre-registration checkpoints
        blank=True,
    )
    email = models.EmailField(null=True, blank=True)  # optional traceability
    token = models.CharField(max_length=255, unique=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Login Checkpoint"
        verbose_name_plural = "Login Checkpoints"
        indexes = [
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        if self.user:
            return f"Checkpoint for {self.user.email}"
        return f"Checkpoint for {self.email or 'unassigned'}"

    @property
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


class OtpRequest(models.Model):
    """One-time password request for email verification or login"""

    EMAIL = "email"
    PHONE = "phone"
    OTP_TYPES = [
        (EMAIL, "Email"),
        (PHONE, "Phone"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="otp_requests",
        null=True,
        blank=True,
    )
    otp_code = models.CharField(max_length=6)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(null=True, blank=True, max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempt_count = models.IntegerField(default=0)
    type = models.CharField(max_length=10, choices=OTP_TYPES, default=EMAIL)
    is_email_delivered = models.BooleanField(default=False)
    is_phone_delivered = models.BooleanField(default=False)

    def clean(self):
        if not self.type in dict(self.OTP_TYPES):
            raise ValidationError({"type": "Invalid OTP type."})

        if not self.email and not self.phone:
            raise ValueError("Either email or phone must be provided.")
        return super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "OTP Request"

    def __str__(self):
        return f"OTP for {self.user.username} - {self.otp_code}"


class UserActivity(models.Model):
    ACTION_TYPES = [
        ("login", "Login"),
        ("logout", "Logout"),
        ("update_profile", "Update Profile"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activities"
    )
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    description = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    location = models.CharField(max_length=250, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        # checker: dapat valid ang action
        valid_actions = [choice[0] for choice in self.ACTION_TYPES]
        if self.action not in valid_actions:
            raise ValidationError(
                f"Invalid action '{self.action}'. Must be one of {valid_actions}"
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.action} at {self.timestamp}"
