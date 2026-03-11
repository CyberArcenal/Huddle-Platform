# serializers/user.py
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from typing import Dict, Any, Optional, List


from users.services.user import UserService

from ..models import User, UserStatus, UserFollow, UserSecuritySettings, UserActivity
from ..enums import UserStatus as UserStatusEnum


class UserBaseSerializer(serializers.ModelSerializer):
    """Base serializer for common user fields and validation"""

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "date_of_birth",
            "phone_number",
            "location",
            "bio",
            "is_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_verified", "created_at", "updated_at"]

    def validate_username(self, value: str) -> str:
        """Validate username uniqueness and format"""
        if not value:
            raise serializers.ValidationError("Username cannot be empty")

        # Check if username already exists (excluding current instance)
        current_user = self.instance
        queryset = User.objects.filter(username__iexact=value)

        if current_user:
            queryset = queryset.exclude(id=current_user.id)

        if queryset.exists():
            raise serializers.ValidationError("Username already exists")

        # Add additional username validation rules
        if len(value) < 3:
            raise serializers.ValidationError(
                "Username must be at least 3 characters long"
            )
        if len(value) > 30:
            raise serializers.ValidationError("Username cannot exceed 30 characters")
        if not value.replace("_", "").replace(".", "").isalnum():
            raise serializers.ValidationError(
                "Username can only contain letters, numbers, underscores and dots"
            )

        return value.lower()

    def validate_email(self, value: str) -> str:
        """Validate email format and uniqueness"""
        if not value:
            raise serializers.ValidationError("Email cannot be empty")

        # Basic email format validation
        if "@" not in value or "." not in value:
            raise serializers.ValidationError("Enter a valid email address")

        # Check if email already exists (excluding current instance)
        current_user = self.instance
        queryset = User.objects.filter(email__iexact=value)

        if current_user:
            queryset = queryset.exclude(id=current_user.id)

        if queryset.exists():
            raise serializers.ValidationError("Email already exists")

        return value.lower()

    def validate_date_of_birth(self, value):
        """Validate date of birth (must be at least 13 years old)"""
        if value:
            min_age_date = timezone.now().date() - timezone.timedelta(days=365 * 13)
            if value > min_age_date:
                raise serializers.ValidationError("You must be at least 13 years old")
        return value


class UserCreateSerializer(UserBaseSerializer):
    """Serializer for user registration/creation"""

    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
        help_text="Password must be at least 8 characters long",
    )
    confirm_password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )

    class Meta(UserBaseSerializer.Meta):
        fields = UserBaseSerializer.Meta.fields + ["password", "confirm_password"]
        read_only_fields = ["id", "is_verified", "created_at", "updated_at"]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the entire registration data"""
        # Check password confirmation
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match"}
            )

        # Validate password strength
        try:
            validate_password(attrs["password"])
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        # Remove confirm_password from validated data
        attrs.pop("confirm_password")

        return attrs

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> User:
        """Create a new user using UserService"""
        try:
            password = validated_data.pop("password")

            # Create user through service layer
            user = UserService.create_user(
                username=validated_data.get("username"),
                email=validated_data.get("email"),
                password=password,
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
                phone_number=validated_data.get("phone_number", ""),
                **{
                    k: v
                    for k, v in validated_data.items()
                    if k
                    not in [
                        "username",
                        "email",
                        "first_name",
                        "last_name",
                        "phone_number",
                    ]
                },
            )

            # Log user creation activity
            UserActivity.objects.create(
                user=user,
                action="account_created",
                description="User account created successfully",
                ip_address=(
                    self.context.get("request").META.get("REMOTE_ADDR")
                    if self.context.get("request")
                    else None
                ),
                user_agent=(
                    self.context.get("request").META.get("HTTP_USER_AGENT")
                    if self.context.get("request")
                    else None
                ),
            )

            return user

        except Exception as e:
            # Log error and re-raise
            raise serializers.ValidationError(str(e))


class UserUpdateSerializer(UserBaseSerializer):
    """Serializer for updating user profile"""

    current_password = serializers.CharField(
        write_only=True,
        required=False,
        style={"input_type": "password"},
        help_text="Required when changing sensitive information",
    )
    new_password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
    )

    class Meta(UserBaseSerializer.Meta):
        fields = UserBaseSerializer.Meta.fields + ["current_password", "new_password"]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate update data"""
        request = self.context.get("request")
        user = request.user if request else None

        # Check if trying to change password
        if "new_password" in attrs:
            if "current_password" not in attrs:
                raise serializers.ValidationError(
                    {
                        "current_password": "Current password is required to set new password"
                    }
                )

            # Verify current password
            if not user.check_password(attrs["current_password"]):
                raise serializers.ValidationError(
                    {"current_password": "Current password is incorrect"}
                )

            # Validate new password strength
            try:
                validate_password(attrs["new_password"], user=user)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"new_password": list(e.messages)})

            # Update password field for service
            attrs["password"] = attrs.pop("new_password")
            attrs.pop("current_password")

        # Check if trying to change email (additional verification might be needed)
        if "email" in attrs and attrs["email"] != user.email:
            # In production, you might want to send verification email
            pass

        return attrs

    @transaction.atomic
    def update(self, instance: User, validated_data: Dict[str, Any]) -> User:
        """Update user information"""
        try:
            # Update user through service layer
            updated_user = UserService.update_user(instance, validated_data)

            # Log profile update activity
            UserActivity.objects.create(
                user=updated_user,
                action="update_profile",
                description="User profile updated",
                ip_address=(
                    self.context.get("request").META.get("REMOTE_ADDR")
                    if self.context.get("request")
                    else None
                ),
                user_agent=(
                    self.context.get("request").META.get("HTTP_USER_AGENT")
                    if self.context.get("request")
                    else None
                ),
                metadata={"updated_fields": list(validated_data.keys())},
            )

            return updated_user

        except Exception as e:
            raise serializers.ValidationError(str(e))


class UserProfileSerializer(UserBaseSerializer):
    """Serializer for detailed user profile view"""

    profile_picture_url = serializers.SerializerMethodField()
    cover_photo_url = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    posts_count = serializers.SerializerMethodField()

    class Meta(UserBaseSerializer.Meta):
        fields = UserBaseSerializer.Meta.fields + [
            "profile_picture_url",
            "cover_photo_url",
            "followers_count",
            "following_count",
            "is_following",
            "posts_count",
            "status",
        ]
        read_only_fields = UserBaseSerializer.Meta.read_only_fields + ["status"]

    def get_profile_picture_url(self, obj: User) -> Optional[str]:
        """Get full URL for profile picture"""
        if obj.profile_picture:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None
    
    def get_posts_count(self, obj):
        from feed.models.base import Post
        return Post.objects.filter(user_id=obj.id).count()

    def get_cover_photo_url(self, obj: User) -> Optional[str]:
        """Get full URL for cover photo"""
        if obj.cover_photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.cover_photo.url)
            return obj.cover_photo.url
        return None

    def get_followers_count(self, obj: User) -> int:
        """Get number of followers"""
        return obj.followers.count()

    def get_following_count(self, obj: User) -> int:
        """Get number of users being followed"""
        return obj.following.count()

    def get_is_following(self, obj: User) -> bool:
        """Check if requesting user is following this user"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return UserFollow.objects.filter(
                follower=request.user, following=obj
            ).exists()
        return False


class UserListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for user listings/search results"""

    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "profile_picture_url",
            "is_verified",
        ]
        read_only_fields = fields

    def get_profile_picture_url(self, obj: User) -> Optional[str]:
        """Get profile picture URL"""
        if obj.profile_picture:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None


class UserStatusSerializer(serializers.Serializer):
    """Serializer for updating user status"""

    status = serializers.ChoiceField(
        choices=[(status.value, status.name) for status in UserStatusEnum],
        required=True,
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Optional reason for status change",
    )

    def validate_status(self, value: str) -> str:
        """Validate status value"""
        valid_statuses = [status.value for status in UserStatusEnum]
        if value not in valid_statuses:
            raise serializers.ValidationError(
                f"Invalid status. Must be one of: {valid_statuses}"
            )
        return value

    def update(self, instance: User, validated_data: Dict[str, Any]) -> User:
        """Update user status"""
        try:
            new_status = validated_data["status"]
            reason = validated_data.get("reason", "")

            # Update status through service
            user = UserService.update_status(instance, new_status)

            # Log status change activity
            UserActivity.objects.create(
                user=user,
                action="status_change",
                description=f"User status changed to {new_status}",
                ip_address=(
                    self.context.get("request").META.get("REMOTE_ADDR")
                    if self.context.get("request")
                    else None
                ),
                user_agent=(
                    self.context.get("request").META.get("HTTP_USER_AGENT")
                    if self.context.get("request")
                    else None
                ),
                metadata={
                    "previous_status": instance.status,
                    "new_status": new_status,
                    "reason": reason,
                },
            )

            return user

        except Exception as e:
            raise serializers.ValidationError(str(e))


class UserFollowSerializer(serializers.ModelSerializer):
    """Serializer for user follow relationships"""

    follower = UserListSerializer(read_only=True)
    following = UserListSerializer(read_only=True)

    class Meta:
        model = UserFollow
        fields = ["id", "follower", "following", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate follow relationship"""
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        # Check if trying to follow self
        if request.user == attrs.get("following"):
            raise serializers.ValidationError("Cannot follow yourself")

        # Check if already following
        if UserFollow.objects.filter(
            follower=request.user, following=attrs.get("following")
        ).exists():
            raise serializers.ValidationError("Already following this user")

        return attrs

    def create(self, validated_data: Dict[str, Any]) -> UserFollow:
        """Create follow relationship"""
        with transaction.atomic():
            follow = UserFollow.objects.create(**validated_data)

            # Log follow activity
            UserActivity.objects.create(
                user=validated_data["follower"],
                action="follow_user",
                description=f"Started following {validated_data['following'].username}",
                metadata={"following_id": validated_data["following"].id},
            )

            return follow


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


class UserActivitySerializer(serializers.ModelSerializer):
    """Serializer for user activity logs"""

    user = UserListSerializer(read_only=True)

    class Meta:
        model = UserActivity
        fields = [
            "id",
            "user",
            "action",
            "description",
            "ip_address",
            "user_agent",
            "timestamp",
            "location",
            "metadata",
        ]
        read_only_fields = fields


class UserMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for user references (e.g. in followers list)"""

    profile_picture_url = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "profile_picture_url", "full_name", "location",]
        read_only_fields = fields

    def get_profile_picture_url(self, obj: User) -> Optional[str]:
        """Get profile picture URL"""
        if obj.profile_picture:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None

    def get_full_name(self, obj: User) -> str:
        """Get full name of the user"""
        return f"{obj.first_name} {obj.last_name}".strip()



class UserProfileSchemaUpdateSerializer(serializers.Serializer):
    """Serializer for updating non-sensitive user profile fields"""

    bio = serializers.CharField(required=False, allow_blank=True, max_length=500)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=20)
    profile_picture = serializers.ImageField(required=False, allow_null=True)
    location = serializers.CharField(required=False, allow_blank=True, max_length=100)

    class Meta:
        fields = ["bio", "phone_number", "profile_picture", "location"]
