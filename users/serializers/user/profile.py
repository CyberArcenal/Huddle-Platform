import logging

from users.models.friendship import Friendship

from users.serializers.user.base import HobbySerializer
from users.serializers.user.minimal import UserMinimalSerializer

import users.services.user_image

import users.models
import rest_framework
import typing
import feed.models.post
import users.services.user_follow
from rest_framework import serializers
from django.db import models

# ---------- Nested serializers for many-to-many fields (read-only) ----------
class PostStatsSerializers(serializers.Serializer):
    comment_count = serializers.IntegerField()
    like_count = serializers.IntegerField()
    reaction_count = serializers.DictField()
    privacy = serializers.ChoiceField(choices=feed.models.post.POST_PRIVACY_TYPES)
    comments = serializers.DictField()
    liked = serializers.BooleanField()
    current_reaction = serializers.StringRelatedField()
    share_count = serializers.IntegerField()
    
    view_count = serializers.IntegerField()
    moots_who_reacted = serializers.ListField()
    unique_viewers = serializers.IntegerField()
    bookmark_count = serializers.IntegerField()
    report_count = serializers.IntegerField()
    is_author = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    trending_score = serializers.FloatField()

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
        

from users.serializers.user_image import UserImageMinimalSerializer
logger = logging.getLogger(__name__)

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
    
    friends_count = serializers.SerializerMethodField()
    friends_preview = serializers.SerializerMethodField()
    mutual_friends_count = serializers.SerializerMethodField()
    
    full_name = rest_framework.serializers.SerializerMethodField()

    class Meta:
        model = users.models.User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
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
            "friends_count",
            "friends_preview",
            "mutual_friends_count",
        ]
        read_only_fields = [
            "id",
            "is_verified",
            "created_at",
            "updated_at",
            "status",
            "email",
            "phone_number",
            "friends_count",
            "friends_preview",
            "mutual_friends_count",
        ]
        
    def get_full_name(self, obj: users.models.User) -> str:
        """Get full name of the user"""
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_profile_picture_url(self, obj: users.models.User) -> typing.Optional[str]:
        from users.services.user_image import UserImageService
        try:
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
        except:
            logger.error(f"Failed to load profile picture")
            return None

    def get_cover_photo_url(self, obj: users.models.User) -> typing.Optional[str]:
        from users.services.user_image import UserImageService

        active = users.services.user_image.UserImageService.get_active_image(obj, "cover")
        try:
            if active and active.is_active:
                request = self.context.get("request")
                if self._can_view_image(request, obj, active):
                    return (
                        request.build_absolute_uri(active.image.url)
                        if request
                        else active.image.url
                    )
        except:
            import traceback; traceback.print_exc();
            logger.error(f"Failed to load image")
            pass
        return None

    def get_profile_picture(self, obj: users.models.User) -> UserImageMinimalSerializer:
        try:
            from users.services.user_image import UserImageService

            active = users.services.user_image.UserImageService.get_active_image(obj, "profile")
            if active and active.is_active:
                request = self.context.get("request")
                # Check privacy
                if self._can_view_image(request, obj, active):
                    return UserImageMinimalSerializer(active, context=self.context).data
            return None
        except:
            logger.error(f"Failed to load profile picture for user {obj.id}")

    def get_cover_photo(self, obj: users.models.User) -> UserImageMinimalSerializer:
        from users.services.user_image import UserImageService
        try:
            active = users.services.user_image.UserImageService.get_active_image(obj, "cover")
            if active and active.is_active:
                request = self.context.get("request")
                if self._can_view_image(request, obj, active):
                    return UserImageMinimalSerializer(active, context=self.context).data
            return None
        except:
            logger.error(f"Failed to load cover photo for user {obj.id}")
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
    
    def get_friends_count(self, obj) -> int:
        """Count accepted friendships where user is either from_user or to_user."""
        return Friendship.objects.filter(
            models.Q(from_user=obj, status='accepted') | models.Q(to_user=obj, status='accepted')
        ).count()

    def get_friends_preview(self, obj) -> UserMinimalSerializer(many=True): # type: ignore
        """Return up to 5 accepted friends (minimal representation)."""
        # Get up to 5 accepted friendships
        friendships = Friendship.objects.filter(
            models.Q(from_user=obj, status='accepted') | models.Q(to_user=obj, status='accepted')
        ).select_related('from_user', 'to_user')[:5]

        # Extract the friend user objects
        friend_users = []
        for f in friendships:
            friend = f.to_user if f.from_user == obj else f.from_user
            friend_users.append(friend)

        # Serialize using the minimal user serializer
        return UserMinimalSerializer(friend_users, many=True, context=self.context).data

    def get_mutual_friends_count(self, obj) -> int:
        """For the authenticated user, count mutual friends with the profile owner."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated or request.user == obj:
            return None

        # Get friend IDs of request.user
        user_friend_ids = set()
        friendships = Friendship.objects.filter(
            models.Q(from_user=request.user, status='accepted') | models.Q(to_user=request.user, status='accepted')
        ).select_related('from_user', 'to_user')
        for f in friendships:
            if f.from_user == request.user:
                user_friend_ids.add(f.to_user.id)
            else:
                user_friend_ids.add(f.from_user.id)

        # Get friend IDs of profile owner (obj)
        obj_friend_ids = set()
        friendships = Friendship.objects.filter(
            models.Q(from_user=obj, status='accepted') | models.Q(to_user=obj, status='accepted')
        ).select_related('from_user', 'to_user')
        for f in friendships:
            if f.from_user == obj:
                obj_friend_ids.add(f.to_user.id)
            else:
                obj_friend_ids.add(f.from_user.id)

        return len(user_friend_ids.intersection(obj_friend_ids))

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