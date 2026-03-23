# serializers/follow_serializer.py
import logging

from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from typing import Dict, Any, List, Optional


from users.enums import UserStatus
from users.serializers.user import UserMinimalSerializer

from ..models import User, UserFollow, UserActivity
from ..services import UserService

logger = logging.getLogger(__name__)

class FollowUserSerializer(serializers.ModelSerializer):
    """Serializer for following a user"""

    following_id = serializers.IntegerField(write_only=True)
    following_username = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = UserFollow
        fields = ["id", "following_id", "following_username", "created_at"]
        read_only_fields = ["id", "following_username", "created_at"]

    def get_following_username(self, obj) -> Optional[str]:
        """Get username of the user being followed"""
        if hasattr(obj, "following"):
            return obj.following.username
        elif "following_id" in self.validated_data:
            try:
                user = User.objects.get(id=self.validated_data["following_id"])
                return user.username
            except User.DoesNotExist:
                return None
        return None

    def validate_following_id(self, value: int) -> int:
        """Validate the user to follow"""
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        # Check if trying to follow self
        if value == request.user.id:
            raise serializers.ValidationError("Cannot follow yourself")

        try:
            following_user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")

        # Check if user is active
        logger.debug(f"User status is {following_user.status}")
        if following_user.status != UserStatus.ACTIVE:
            raise serializers.ValidationError("Cannot follow inactive user")

        # Check if already following
        if UserFollow.objects.filter(
            follower=request.user, following=following_user
        ).exists():
            raise serializers.ValidationError("Already following this user")

        return value

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> UserFollow:
        """Create follow relationship"""
        request = self.context.get("request")
        following_user = User.objects.get(id=validated_data["following_id"])

        # Create follow relationship
        follow = UserFollow.objects.create(
            follower=request.user, following=following_user
        )

        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action="follow_user",
            description=f"Started following {following_user.username}",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
            metadata={"following_id": following_user.id},
        )

        return follow


class UnfollowUserSerializer(serializers.Serializer):
    """Serializer for unfollowing a user"""

    following_id = serializers.IntegerField(required=True)

    def validate_following_id(self, value: int) -> int:
        """Validate the user to unfollow"""
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        try:
            following_user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")

        # Check if actually following
        if not UserFollow.objects.filter(
            follower=request.user, following=following_user
        ).exists():
            raise serializers.ValidationError("Not following this user")

        return value

    def unfollow(self) -> bool:
        """Remove follow relationship"""
        request = self.context.get("request")
        following_id = self.validated_data["following_id"]

        try:
            with transaction.atomic():
                # Get and delete follow relationship
                follow = UserFollow.objects.get(
                    follower=request.user, following_id=following_id
                )
                follow.delete()

                # Log activity
                UserActivity.objects.create(
                    user=request.user,
                    action="unfollow_user",
                    description=f"Stopped following user ID: {following_id}",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                    metadata={"unfollowed_user_id": following_id},
                )

                return True
        except UserFollow.DoesNotExist:
            return False


class FollowStatsSerializer(serializers.Serializer):
    """Serializer for follow statistics"""

    followers_count = serializers.IntegerField()
    following_count = serializers.IntegerField()
    mutual_followers_count = serializers.IntegerField()

    def to_representation(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        """Format the statistics"""
        return {
            "followers": instance.get("followers_count", 0),
            "following": instance.get("following_count", 0),
            "mutual": instance.get("mutual_followers_count", 0),
        }


class FollowerListSerializer(serializers.ModelSerializer):
    """Serializer for listing followers"""

    follower_id = serializers.IntegerField(source="follower.id")
    follower_username = serializers.CharField(source="follower.username")
    follower_name = serializers.SerializerMethodField()
    follower_avatar = serializers.SerializerMethodField()
    is_following_back = serializers.SerializerMethodField()

    class Meta:
        model = UserFollow
        fields = [
            "follower_id",
            "follower_username",
            "follower_name",
            "follower_avatar",
            "is_following_back",
            "created_at",
        ]

    def get_follower_name(self, obj) -> str:
        """Get follower's full name"""
        user = obj.follower
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        return user.username

    def get_follower_avatar(self, obj) -> Optional[str]:
        """Get follower's profile picture URL"""
        request = self.context.get("request")
        if obj.follower.profile_picture:
            if request:
                return request.build_absolute_uri(obj.follower.profile_picture.url)
            return obj.follower.profile_picture.url
        return None

    def get_is_following_back(self, obj) -> bool:
        """Check if the user is following back"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return UserFollow.objects.filter(
                follower=obj.following, following=obj.follower
            ).exists()
        return False


class FollowingListSerializer(serializers.ModelSerializer):
    """Serializer for listing users being followed"""

    following_id = serializers.IntegerField(source="following.id")
    following_username = serializers.CharField(source="following.username")
    following_name = serializers.SerializerMethodField()
    following_avatar = serializers.SerializerMethodField()
    is_following_back = serializers.SerializerMethodField()

    class Meta:
        model = UserFollow
        fields = [
            "following_id",
            "following_username",
            "following_name",
            "following_avatar",
            "is_following_back",
            "created_at",
        ]

    def get_following_name(self, obj) -> str:
        """Get followed user's full name"""
        user = obj.following
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        return user.username

    def get_following_avatar(self, obj) -> Optional[str]:
        """Get followed user's profile picture URL"""
        request = self.context.get("request")
        if obj.following.profile_picture:
            if request:
                return request.build_absolute_uri(obj.following.profile_picture.url)
            return obj.following.profile_picture.url
        return None

    def get_is_following_back(self, obj) -> bool:
        """Check if followed user is following back"""
        return UserFollow.objects.filter(
            follower=obj.following, following=obj.follower
        ).exists()
        

class UserFollowSerializer(serializers.ModelSerializer):
    """Serializer for user follow relationships"""
    follower = UserMinimalSerializer(read_only=True)
    following = UserMinimalSerializer(read_only=True)

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
        
        
# ===== Response serializers for drf-spectacular =====

class FollowBasicSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    follower_id = serializers.IntegerField()
    following_id = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class FollowUserResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    follow = FollowBasicSerializer()


class UnfollowUserResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class FollowStatusResponseSerializer(serializers.Serializer):
    is_following = serializers.BooleanField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()


class FollowStatsResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    stats = FollowStatsSerializer()  # reuses the existing serializer
