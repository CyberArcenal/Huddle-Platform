# serializers/user.py
import users.services.user_image

import users.models
import users.enums
import rest_framework
import django.contrib.auth.password_validation
import django.core.exceptions
import django.db
import django.utils
import typing
import feed.models.post
import users.models.user
import users.services.user
import users.services.user_follow
from rest_framework import serializers


# ---------- Nested serializers for many-to-many fields (read-only) ----------
class ReactionCountSerializer(serializers.Serializer):
    # dynamic fields per reaction type
    like = serializers.IntegerField(default=0)
    love = serializers.IntegerField(default=0)
    care = serializers.IntegerField(default=0)
    haha = serializers.IntegerField(default=0)
    wow = serializers.IntegerField(default=0)
    sad = serializers.IntegerField(default=0)
    angry = serializers.IntegerField(default=0)


class PostStatsSerializers(serializers.Serializer):
    comment_count = serializers.IntegerField()
    like_count = serializers.IntegerField()
    reaction_count = ReactionCountSerializer()
    privacy = serializers.ChoiceField(choices=["public", "followers", "secret"])
    comments = serializers.DictField()
    liked = serializers.BooleanField()
    current_reaction = serializers.StringRelatedField()

class InterestSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.Interest
        fields = ["id", "name"]


class FavoriteSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.Favorite
        fields = ["id", "name"]


class MusicSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.Music
        fields = ["id", "name"]


class WorkSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.Work
        fields = ["id", "name"]


class SchoolSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.School
        fields = ["id", "name"]


class AchievementSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.Achievement
        fields = ["id", "name"]


class SocialCauseSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.SocialCause
        fields = ["id", "name"]


class LifestyleTagSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.LifestyleTag
        fields = ["id", "name"]
        
class HobbySerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.Hobby
        fields = ["id", "name"]

class UserImageMinimalSerializer(rest_framework.serializers.ModelSerializer):
    image_url = rest_framework.serializers.SerializerMethodField()
    statistics = rest_framework.serializers.SerializerMethodField()

    class Meta:
        model = users.models.user.UserImage
        fields = ["id", "image_url", "caption", "image_type", "is_active", "created_at", "statistics"]

    def get_image_url(self, obj):
        if obj.image:
            return self.context["request"].build_absolute_uri(obj.image.url)
        return None
    
    def get_statistics(
        self, obj
    ) -> PostStatsSerializers:
        from feed.services.post import PostService

        return PostService.get_post_statistics(serializer=self, obj=obj)


class UserMinimalSerializer(rest_framework.serializers.ModelSerializer):
    """Minimal serializer for user references (e.g. in followers list)"""

    profile_picture_url = rest_framework.serializers.SerializerMethodField()
    full_name = rest_framework.serializers.SerializerMethodField()
    hobbies = HobbySerializer(many=True, read_only=True)
    capability_score = rest_framework.serializers.IntegerField(required=False)
    reasons = rest_framework.serializers.ListField(child=rest_framework.serializers.CharField(), required=False)
    is_following = rest_framework.serializers.SerializerMethodField()

    class Meta:
        model = users.models.User
        fields = [
            "id",
            "username",
            "profile_picture_url",
            "personality_type",
            "hobbies",
            "full_name",
            "location",
            "capability_score",
            "reasons",
            "is_following",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"required": True, "allow_null": False},
            "username": {"required": True, "allow_null": False},
        }

    def get_is_following(self, obj: users.models.User) -> bool:
        request = self.context.get("request", None)
        if request and request.user.is_authenticated and request.user != obj:
            return users.services.user_follow.UserFollowService.is_following(request.user, obj)
        return False

    def get_profile_picture_url(self, obj: users.models.User) -> typing.Optional[str]:
        from users.services.user_image import UserImageService

        active = users.services.user_image.UserImageService.get_active_image(obj, "profile")
        if active and active.is_active:
            request = self.context.get("request")
            if not request or not request.user.is_authenticated:
                return (
                    request.build_absolute_uri(active.image.url)
                    if active.image.privacy == "public"
                    else None
                )
            if request.user == obj:
                return request.build_absolute_uri(active.image.url)
            if active.image.privacy == "public":
                return request.build_absolute_uri(active.image.url)
            if active.image.privacy == "followers" and users.services.user_follow.UserFollowService.is_following(
                request.user, obj
            ):
                return request.build_absolute_uri(active.image.url)
            return None
        return None

    def get_full_name(self, obj: users.models.User) -> str:
        """Get full name of the user"""
        return f"{obj.first_name} {obj.last_name}".strip()

    def to_representation(self, instance):
        """Remove capability_score if not set"""
        data = super().to_representation(instance)
        if data.get("capability_score") is None:
            data.pop("capability_score", None)
        if not data.get("reasons"):
            data.pop("reasons", None)
        return data





# ---------- User Serializers ----------
class UserBaseSerializer(rest_framework.serializers.ModelSerializer):
    """Base serializer for common user fields and validation"""

    username = rest_framework.serializers.CharField(
        max_length=30,
        min_length=3,
        help_text="Username (3-30 characters, letters, numbers, underscores, dots)",
    )
    email = rest_framework.serializers.EmailField(help_text="Valid email address")
    first_name = rest_framework.serializers.CharField(required=False, allow_blank=True, max_length=30)
    last_name = rest_framework.serializers.CharField(required=False, allow_blank=True, max_length=30)
    # Write-only fields for many-to-many relationships (accept list of IDs)
    hobbies = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=users.models.Hobby.objects.all(), many=True, required=False, write_only=True
    )
    interests = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=users.models.Interest.objects.all(), many=True, required=False, write_only=True
    )
    favorites = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=users.models.Favorite.objects.all(), many=True, required=False, write_only=True
    )
    favorite_music = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=users.models.Music.objects.all(), many=True, required=False, write_only=True
    )
    works = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=users.models.Work.objects.all(), many=True, required=False, write_only=True
    )
    schools = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=users.models.School.objects.all(), many=True, required=False, write_only=True
    )
    achievements = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=users.models.Achievement.objects.all(), many=True, required=False, write_only=True
    )
    causes = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=users.models.SocialCause.objects.all(), many=True, required=False, write_only=True
    )
    lifestyle_tags = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=users.models.LifestyleTag.objects.all(), many=True, required=False, write_only=True
    )

    class Meta:
        model = users.models.User
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
            # New fields
            "personality_type",
            "love_language",
            "relationship_goal",
            "latitude",
            "longitude",
            "hobbies",
            "interests",
            "favorites",
            "favorite_music",
            "works",
            "schools",
            "achievements",
            "causes",
            "lifestyle_tags",
        ]
        read_only_fields = ["id", "is_verified", "created_at", "updated_at"]

    def validate_username(self, value: str) -> str:
        """Validate username uniqueness and format"""
        if not value:
            raise rest_framework.serializers.ValidationError("Username cannot be empty")

        # Check if username already exists (excluding current instance)
        current_user = self.instance
        queryset = users.models.User.objects.filter(username__iexact=value)

        if current_user:
            queryset = queryset.exclude(id=current_user.id)

        if queryset.exists():
            raise rest_framework.serializers.ValidationError("Username already exists")

        # Add additional username validation rules
        if len(value) < 3:
            raise rest_framework.serializers.ValidationError(
                "Username must be at least 3 characters long"
            )
        if len(value) > 30:
            raise rest_framework.serializers.ValidationError("Username cannot exceed 30 characters")
        if not value.replace("_", "").replace(".", "").isalnum():
            raise rest_framework.serializers.ValidationError(
                "Username can only contain letters, numbers, underscores and dots"
            )

        return value.lower()

    def validate_email(self, value: str) -> str:
        """Validate email format and uniqueness"""
        if not value:
            raise rest_framework.serializers.ValidationError("Email cannot be empty")

        # Basic email format validation
        if "@" not in value or "." not in value:
            raise rest_framework.serializers.ValidationError("Enter a valid email address")

        # Check if email already exists (excluding current instance)
        current_user = self.instance
        queryset = users.models.User.objects.filter(email__iexact=value)

        if current_user:
            queryset = queryset.exclude(id=current_user.id)

        if queryset.exists():
            raise rest_framework.serializers.ValidationError("Email already exists")

        return value.lower()

    def validate_date_of_birth(self, value):
        """Validate date of birth (must be at least 13 years old)"""
        if value:
            min_age_date = django.utils.timezone.now().date() - django.utils.timezone.timedelta(days=365 * 13)
            if value > min_age_date:
                raise rest_framework.serializers.ValidationError("You must be at least 13 years old")
        return value

    def validate_personality_type(self, value):
        """Validate personality type (MBTI)"""
        if value and value not in dict(users.models.MBTIType.choices):
            raise rest_framework.serializers.ValidationError("Invalid personality type")
        return value

    def validate_love_language(self, value):
        """Validate love language"""
        if value and value not in dict(users.models.LoveLanguage.choices):
            raise rest_framework.serializers.ValidationError("Invalid love language")
        return value


class UserMinimalSerializer(rest_framework.serializers.ModelSerializer):
    """Minimal serializer for user references (e.g. in followers list)"""

    profile_picture_url = rest_framework.serializers.SerializerMethodField()
    full_name = rest_framework.serializers.SerializerMethodField()
    hobbies = HobbySerializer(many=True, read_only=True)
    capability_score = rest_framework.serializers.IntegerField(required=False)
    reasons = rest_framework.serializers.ListField(child=rest_framework.serializers.CharField(), required=False)
    is_following = rest_framework.serializers.SerializerMethodField()

    class Meta:
        model = users.models.User
        fields = [
            "id",
            "username",
            "profile_picture_url",
            "personality_type",
            "hobbies",
            "full_name",
            "location",
            "capability_score",
            "reasons",
            "is_following",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"required": True, "allow_null": False},
            "username": {"required": True, "allow_null": False},
        }

    def get_is_following(self, obj: users.models.User) -> bool:
        request = self.context.get("request", None)
        if request and request.user.is_authenticated and request.user != obj:
            return users.services.user_follow.UserFollowService.is_following(request.user, obj)
        return False

    def get_profile_picture_url(self, obj: users.models.User) -> typing.Optional[str]:
        active = users.services.user_image.UserImageService.get_active_image(obj, "profile")
        if active and active.is_active:
            request = self.context.get("request")
            if not request or not request.user.is_authenticated:
                return (
                    request.build_absolute_uri(active.image.url)
                    if active.image.privacy == "public"
                    else None
                )
            if request.user == obj:
                return request.build_absolute_uri(active.image.url)
            if active.image.privacy == "public":
                return request.build_absolute_uri(active.image.url)
            if active.image.privacy == "followers" and users.services.user_follow.UserFollowService.is_following(
                request.user, obj
            ):
                return request.build_absolute_uri(active.image.url)
            return None
        return None

    def get_full_name(self, obj: users.models.User) -> str:
        """Get full name of the user"""
        return f"{obj.first_name} {obj.last_name}".strip()

    def to_representation(self, instance):
        """Remove capability_score if not set"""
        data = super().to_representation(instance)
        if data.get("capability_score") is None:
            data.pop("capability_score", None)
        if not data.get("reasons"):
            data.pop("reasons", None)
        return data


class UserCreateSerializer(UserBaseSerializer):
    """Serializer for user registration/creation"""

    password = rest_framework.serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
        help_text="Password must be at least 8 characters long",
    )
    confirm_password = rest_framework.serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )

    class Meta(UserBaseSerializer.Meta):
        fields = UserBaseSerializer.Meta.fields + ["password", "confirm_password"]
        read_only_fields = ["id", "is_verified", "created_at", "updated_at"]

    def validate(self, attrs: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        """Validate the entire registration data"""
        # Check password confirmation
        if attrs["password"] != attrs["confirm_password"]:
            raise rest_framework.serializers.ValidationError(
                {"confirm_password": "Passwords do not match"}
            )

        # Validate password strength
        try:
            django.contrib.auth.password_validation.validate_password(attrs["password"])
        except django.core.exceptions.ValidationError as e:
            raise rest_framework.serializers.ValidationError({"password": list(e.messages)})

        # Remove confirm_password from validated data
        attrs.pop("confirm_password")

        return attrs

    @django.db.transaction.atomic
    def create(self, validated_data: typing.Dict[str, typing.Any]) -> users.models.User:
        """Create a new user using UserService"""
        try:
            # Extract many-to-many fields (they will be set after user creation)
            many_to_many_fields = [
                "hobbies",
                "interests",
                "favorites",
                "favorite_music",
                "works",
                "schools",
                "achievements",
                "causes",
                "lifestyle_tags",
            ]
            many_to_many_data = {}
            for field in many_to_many_fields:
                if field in validated_data:
                    many_to_many_data[field] = validated_data.pop(field)

            password = validated_data.pop("password")

            # Create user through service layer, passing is_active=False
            user = users.services.user.UserService.create_user(
                username=validated_data.get("username"),
                email=validated_data.get("email"),
                password=password,
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
                phone_number=validated_data.get("phone_number", ""),
                is_active=False,  # <-- new flag
                **validated_data,
            )

            # Set many-to-many relationships
            for field, value in many_to_many_data.items():
                getattr(user, field).set(value)

            # Log user creation activity
            users.models.UserActivity.objects.create(
                user=user,
                action="account_created",
                description="User account created (pending verification)",
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
            raise rest_framework.serializers.ValidationError(str(e))


class UserUpdateSerializer(UserBaseSerializer):
    """Serializer for updating user profile"""

    current_password = rest_framework.serializers.CharField(
        write_only=True,
        required=False,
        style={"input_type": "password"},
        help_text="Required when changing sensitive information",
    )
    new_password = rest_framework.serializers.CharField(
        write_only=True,
        required=False,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
    )

    class Meta(UserBaseSerializer.Meta):
        fields = UserBaseSerializer.Meta.fields + ["current_password", "new_password"]

    def validate(self, attrs: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        """Validate update data"""
        request = self.context.get("request")
        user = request.user if request else None

        # Check if trying to change password
        if "new_password" in attrs:
            if "current_password" not in attrs:
                raise rest_framework.serializers.ValidationError(
                    {
                        "current_password": "Current password is required to set new password"
                    }
                )

            # Verify current password
            if not user.check_password(attrs["current_password"]):
                raise rest_framework.serializers.ValidationError(
                    {"current_password": "Current password is incorrect"}
                )

            # Validate new password strength
            try:
                django.contrib.auth.password_validation.validate_password(attrs["new_password"], user=user)
            except django.core.exceptions.ValidationError as e:
                raise rest_framework.serializers.ValidationError({"new_password": list(e.messages)})

            # Update password field for service
            attrs["password"] = attrs.pop("new_password")
            attrs.pop("current_password")

        return attrs

    @django.db.transaction.atomic
    def update(self, instance: users.models.User, validated_data: typing.Dict[str, typing.Any]) -> users.models.User:
        """Update user information"""
        try:
            # Extract many-to-many fields
            many_to_many_fields = [
                "hobbies",
                "interests",
                "favorites",
                "favorite_music",
                "works",
                "schools",
                "achievements",
                "causes",
                "lifestyle_tags",
            ]
            many_to_many_data = {}
            for field in many_to_many_fields:
                if field in validated_data:
                    many_to_many_data[field] = validated_data.pop(field)

            # Update user through service layer
            updated_user = users.services.user.UserService.update_user(instance, validated_data)

            # Update many-to-many relationships
            for field, value in many_to_many_data.items():
                getattr(updated_user, field).set(value)

            # Log profile update activity
            users.models.UserActivity.objects.create(
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
                metadata={
                    "updated_fields": list(validated_data.keys())
                    + list(many_to_many_data.keys())
                },
            )

            return updated_user

        except Exception as e:
            raise rest_framework.serializers.ValidationError(str(e))


class UserProfileSerializer(rest_framework.serializers.ModelSerializer):
    """Serializer for detailed user profile view"""

    username = rest_framework.serializers.CharField(
        max_length=30,
        min_length=3,
        help_text="Username (3-30 characters, letters, numbers, underscores, dots)",
    )
    email = rest_framework.serializers.EmailField(help_text="Valid email address")
    first_name = rest_framework.serializers.CharField(required=False, allow_blank=True, max_length=30)
    last_name = rest_framework.serializers.CharField(required=False, allow_blank=True, max_length=30)
    # Override many-to-many fields to use nested serializers (read-only)
    hobbies = HobbySerializer(many=True, read_only=True)
    interests = InterestSerializer(many=True, read_only=True)
    favorites = FavoriteSerializer(many=True, read_only=True)
    favorite_music = MusicSerializer(many=True, read_only=True)
    works = WorkSerializer(many=True, read_only=True)
    schools = SchoolSerializer(many=True, read_only=True)
    achievements = AchievementSerializer(many=True, read_only=True)
    causes = SocialCauseSerializer(many=True, read_only=True)
    lifestyle_tags = LifestyleTagSerializer(many=True, read_only=True)

    profile_picture_url = rest_framework.serializers.SerializerMethodField()
    cover_photo_url = rest_framework.serializers.SerializerMethodField()
    profile_picture = rest_framework.serializers.SerializerMethodField()
    cover_photo = rest_framework.serializers.SerializerMethodField()

    followers_count = rest_framework.serializers.SerializerMethodField()
    following_count = rest_framework.serializers.SerializerMethodField()
    is_following = rest_framework.serializers.SerializerMethodField()
    posts_count = rest_framework.serializers.SerializerMethodField()
    capability_score = rest_framework.serializers.IntegerField(required=False)
    reasons = rest_framework.serializers.ListField(child=rest_framework.serializers.CharField(), required=False)

    class Meta:
        model = users.models.User
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
            # New fields
            "personality_type",
            "love_language",
            "relationship_goal",
            "latitude",
            "longitude",
            "hobbies",
            "interests",
            "favorites",
            "favorite_music",
            "works",
            "schools",
            "achievements",
            "causes",
            "lifestyle_tags",
            "capability_score",
            "reasons",
            # Computed fields
            "profile_picture_url",
            "cover_photo_url",
            "profile_picture",
            "cover_photo",
            "followers_count",
            "following_count",
            "is_following",
            "posts_count",
            "status",
        ]
        read_only_fields = [
            "id",
            "is_verified",
            "created_at",
            "updated_at",
            "status",
            "email",
            "phone_number",  # Sensitive fields are read-only for others
        ]

    def get_profile_picture_url(self, obj: users.models.User) -> typing.Optional[str]:
        from users.services.user_image import UserImageService

        active = users.services.user_image.UserImageService.get_active_image(obj, "profile")
        if active and active.is_active:
            request = self.context.get("request")
            # Check privacy
            if self._can_view_image(request, obj, active):
                return (
                    request.build_absolute_uri(active.image.url)
                    if request
                    else active.image.url
                )
        return None

    def get_cover_photo_url(self, obj: users.models.User) -> typing.Optional[str]:
        from users.services.user_image import UserImageService

        active = users.services.user_image.UserImageService.get_active_image(obj, "cover")
        if active and active.is_active:
            request = self.context.get("request")
            if self._can_view_image(request, obj, active):
                return (
                    request.build_absolute_uri(active.image.url)
                    if request
                    else active.image.url
                )
        return None

    def get_profile_picture(self, obj: users.models.User) -> UserImageMinimalSerializer:
        from users.services.user_image import UserImageService

        active = users.services.user_image.UserImageService.get_active_image(obj, "profile")
        if active and active.is_active:
            request = self.context.get("request")
            # Check privacy
            if self._can_view_image(request, obj, active):
                return UserImageMinimalSerializer(active, context=self.context).data
        return None

    def get_cover_photo(self, obj: users.models.User) -> UserImageMinimalSerializer:
        from users.services.user_image import UserImageService

        active = users.services.user_image.UserImageService.get_active_image(obj, "cover")
        if active and active.is_active:
            request = self.context.get("request")
            if self._can_view_image(request, obj, active):
                return UserImageMinimalSerializer(active, context=self.context).data
        return None

    def get_followers_count(self, obj: users.models.User) -> int:
        return obj.followers.count()

    def get_following_count(self, obj: users.models.User) -> int:
        return obj.following.count()

    def get_is_following(self, obj: users.models.User) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user != obj:
            return users.services.user_follow.UserFollowService.is_following(request.user, obj)
        return False

    def _can_view_image(self, request, user, image):
        """Check privacy rules for the image."""
        if not request or not request.user.is_authenticated:
            return image.privacy == "public"
        if request.user == user:
            return True
        if image.privacy == "public":
            return True
        if image.privacy == "followers":
            return users.services.user_follow.UserFollowService.is_following(request.user, user)
        return False  # secret or other

    def get_posts_count(self, obj) -> int:
        return feed.models.post.Post.objects.filter(user_id=obj.id).count()

    def to_representation(self, instance):
        """Remove is_following when viewing own profile."""
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request and request.user == instance:
            data.pop("is_following", None)
        if data.get("capability_score") is None:
            data.pop("capability_score", None)
        if not data.get("reasons"):
            data.pop("reasons", None)

        return data


class UserListSerializer(rest_framework.serializers.ModelSerializer):
    """Lightweight serializer for user listings/search results"""

    profile_picture_url = rest_framework.serializers.SerializerMethodField()
    is_following = rest_framework.serializers.SerializerMethodField()
    hobbies = HobbySerializer(many=True, read_only=True)
    capability_score = rest_framework.serializers.IntegerField(required=False)
    reasons = rest_framework.serializers.ListField(child=rest_framework.serializers.CharField(), required=False)

    class Meta:
        model = users.models.User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "profile_picture_url",
            "is_following",
            "is_verified",
            "personality_type",
            "hobbies",
            "capability_score",
            "reasons",
        ]
        read_only_fields = fields

    def get_profile_picture_url(self, obj: users.models.User) -> typing.Optional[str]:
        from users.services.user_image import UserImageService

        active = users.services.user_image.UserImageService.get_active_image(obj, "profile")
        if active and active.is_active:
            request = self.context.get("request")
            # For list views, we can show only public profile pictures to non‑owners
            if not request or not request.user.is_authenticated:
                return (
                    request.build_absolute_uri(active.image.url)
                    if active.image.privacy == "public"
                    else None
                )
            if request.user == obj:
                return request.build_absolute_uri(active.image.url)
            # For other users, check privacy (public or followers)
            if active.image.privacy == "public":
                return request.build_absolute_uri(active.image.url)
            if active.image.privacy == "followers" and users.services.user_follow.UserFollowService.is_following(
                request.user, obj
            ):
                return request.build_absolute_uri(active.image.url)
            return None
        return None

    def get_is_following(self, obj: users.models.User) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user != obj:
            return users.services.user_follow.UserFollowService.is_following(request.user, obj)
        return False

    def to_representation(self, instance):
        """Remove capability_score if not set"""
        data = super().to_representation(instance)
        if data.get("capability_score") is None:
            data.pop("capability_score", None)
        if not data.get("reasons"):
            data.pop("reasons", None)

        return data


class UserStatusSerializer(rest_framework.serializers.Serializer):
    """Serializer for updating user status"""

    status = rest_framework.serializers.ChoiceField(
        choices=[(status.value, status.name) for status in users.enums.UserStatus],
        required=True,
    )
    reason = rest_framework.serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Optional reason for status change",
    )

    def validate_status(self, value: str) -> str:
        """Validate status value"""
        valid_statuses = [status.value for status in users.enums.UserStatus]
        if value not in valid_statuses:
            raise rest_framework.serializers.ValidationError(
                f"Invalid status. Must be one of: {valid_statuses}"
            )
        return value

    def update(self, instance: users.models.User, validated_data: typing.Dict[str, typing.Any]) -> users.models.User:
        """Update user status"""
        try:
            new_status = validated_data["status"]
            reason = validated_data.get("reason", "")

            # Update status through service
            user = users.services.user.UserService.update_status(instance, new_status)

            # Log status change activity
            users.models.UserActivity.objects.create(
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
            raise rest_framework.serializers.ValidationError(str(e))


class UserProfileSchemaUpdateSerializer(rest_framework.serializers.Serializer):
    """Serializer for updating non-sensitive user profile fields"""

    bio = rest_framework.serializers.CharField(required=False, allow_blank=True, max_length=500)
    phone_number = rest_framework.serializers.CharField(
        required=False, allow_blank=True, max_length=20
    )
    location = rest_framework.serializers.CharField(required=False, allow_blank=True, max_length=100)
    # New fields that can be updated directly
    personality_type = rest_framework.serializers.ChoiceField(choices=users.models.MBTIType.choices, required=False)
    love_language = rest_framework.serializers.ChoiceField(
        choices=users.models.LoveLanguage.choices, required=False
    )
    relationship_goal = rest_framework.serializers.CharField(
        required=False, max_length=50, allow_blank=True
    )
    latitude = rest_framework.serializers.FloatField(required=False, allow_null=True)
    longitude = rest_framework.serializers.FloatField(required=False, allow_null=True)

    class Meta:
        fields = [
            "bio",
            "phone_number",
            "location",
            "personality_type",
            "love_language",
            "relationship_goal",
            "latitude",
            "longitude",
        ]


class UserRegisterSerializer(rest_framework.serializers.Serializer):
    """
    Serializer for user registration (minimal fields).
    """

    username = rest_framework.serializers.CharField(
        max_length=30,
        min_length=3,
        help_text="Username (3-30 characters, letters, numbers, underscores, dots)",
    )
    email = rest_framework.serializers.EmailField()
    password = rest_framework.serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
        help_text="Password must be at least 8 characters long",
    )
    confirm_password = rest_framework.serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        required=True,
    )
    first_name = rest_framework.serializers.CharField(required=False, allow_blank=True, max_length=30)
    last_name = rest_framework.serializers.CharField(required=False, allow_blank=True, max_length=30)
    phone_number = rest_framework.serializers.CharField(
        required=False, allow_blank=True, max_length=20
    )

    def validate_username(self, value: str) -> str:
        """Validate username format and uniqueness."""
        if not value:
            raise rest_framework.serializers.ValidationError("Username cannot be empty")
        if len(value) < 3:
            raise rest_framework.serializers.ValidationError(
                "Username must be at least 3 characters long"
            )
        if len(value) > 30:
            raise rest_framework.serializers.ValidationError("Username cannot exceed 30 characters")
        if not value.replace("_", "").replace(".", "").isalnum():
            raise rest_framework.serializers.ValidationError(
                "Username can only contain letters, numbers, underscores and dots"
            )
        # Check uniqueness (case‑insensitive)
        if users.models.User.objects.filter(username__iexact=value).exists():
            raise rest_framework.serializers.ValidationError("Username already exists")
        return value.lower()

    def validate_email(self, value: str) -> str:
        """Validate email format and uniqueness."""
        if not value:
            raise rest_framework.serializers.ValidationError("Email cannot be empty")
        if users.models.User.objects.filter(email__iexact=value).exists():
            raise rest_framework.serializers.ValidationError("Email already exists")
        return value.lower()

    def validate(self, attrs):
        """Cross-field validation: passwords must match and be strong."""
        if attrs["password"] != attrs["confirm_password"]:
            raise rest_framework.serializers.ValidationError(
                {"confirm_password": "Passwords do not match"}
            )
        try:
            django.contrib.auth.password_validation.validate_password(attrs["password"])
        except django.core.exceptions.ValidationError as e:
            raise rest_framework.serializers.ValidationError({"password": list(e.messages)})
        # Remove confirm_password so it doesn't go to the service
        attrs.pop("confirm_password")
        return attrs

    @django.db.transaction.atomic
    def create(self, validated_data):
        """Create a new user with is_active=False (pending verification)."""
        try:
            user = users.services.user.UserService.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
                phone_number=validated_data.get("phone_number", ""),
                is_active=False,  # user must verify email
            )
            # Log the registration
            users.models.UserActivity.objects.create(
                user=user,
                action="account_created",
                description="User account created (pending verification)",
                ip_address=self.context.get("request").META.get("REMOTE_ADDR"),
                user_agent=self.context.get("request").META.get("HTTP_USER_AGENT"),
            )
            return user
        except Exception as e:
            # Re-raise as a ValidationError to be caught by the view
            raise rest_framework.serializers.ValidationError(str(e))
