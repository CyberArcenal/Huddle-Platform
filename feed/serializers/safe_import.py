from typing import Optional

from rest_framework import serializers
from feed.models.comment import Comment
from feed.models.post import Post
from feed.serializers.media import MediaDisplaySerializer
from groups.models.group import Group
from users.models.user import Hobby, User


class GroupMinimalSerializer(serializers.ModelSerializer):
    group_type_display = serializers.CharField(source='get_group_type_display', read_only=True)

    # Extra display fields
    short_description = serializers.SerializerMethodField()
    formatted_member_count = serializers.SerializerMethodField()
    member_preview = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            'id',
            'name',
            'profile_picture',
            'member_count',
            'group_type',
            'group_type_display',
            'short_description',
            'formatted_member_count',
            'member_preview',
            'is_member'
        ]
        read_only_fields = fields

    def get_short_description(self, obj) -> str:
        desc = getattr(obj, 'description', '') or ''
        max_len = 120
        if len(desc) <= max_len:
            return desc
        return desc[:max_len].rsplit(' ', 1)[0] + '…'

    def get_formatted_member_count(self, obj) -> str:
        try:
            n = int(getattr(obj, 'member_count', 0) or 0)
        except Exception:
            n = 0
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}k"
        return str(n)

    def get_member_preview(self, obj) -> serializers.DictField:
        from groups.serializers.member import GroupMemberMinimalSerializer
        """Return up to 3 preview members serialized."""
        members_qs = getattr(obj, 'members_preview', None)
        if not members_qs:
            return []
        serializer = GroupMemberMinimalSerializer(members_qs[:3], many=True, context=self.context)
        return serializer.data

    def get_is_member(self, obj) -> bool:
        request = self.context.get('request', None)
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        # Use annotated attribute if present
        if hasattr(obj, 'is_member_for_user'):
            return bool(getattr(obj, 'is_member_for_user'))
        # Fallback: check membership (may hit DB)
        try:
            return obj.memberships.filter(user_id=user.id).exists()
        except Exception:
            return False


class HobbySerializer(serializers.ModelSerializer):
    class Meta:
        model = Hobby
        fields = ["id", "name"]

class UserMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for user references (e.g. in followers list)"""

    profile_picture_url = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    hobbies = HobbySerializer(many=True, read_only=True)
    capability_score = serializers.IntegerField(required=False)
    reasons = serializers.ListField(child=serializers.CharField(), required=False)
    is_following = serializers.SerializerMethodField()

    class Meta:
        model = User
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

    def get_is_following(self, obj: User) -> bool:
        from users.services.user_follow import UserFollowService
        request = self.context.get("request", None)
        if request and request.user.is_authenticated and request.user != obj:
            return UserFollowService.is_following(request.user, obj)
        return False

    def get_profile_picture_url(self, obj: User) -> Optional[str]:
        from users.services.user_follow import UserFollowService
        from users.services.user_image import UserImageService
        active = UserImageService.get_active_image(obj, "profile")
        if active and active.is_active:
            request = self.context.get("request")
            if not request or not request.user.is_authenticated:
                
                return (
                    request.build_absolute_uri(active.image.url)
                    if active.privacy == "public"
                    
                    else None
                )
            if request.user == obj:
                return request.build_absolute_uri(active.image.url)
            if active.privacy == "public":
                return request.build_absolute_uri(active.image.url)
            if active.privacy == "followers" and UserFollowService.is_following(
                request.user, obj
            ):
                return request.build_absolute_uri(active.image.url)
            return None
        return None

    def get_full_name(self, obj: User) -> str:
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
    
    
class CommentDisplaySerializerNoReplies(serializers.ModelSerializer):
    """Detailed view for a comment without nested replies."""

    user = UserMinimalSerializer(read_only=True)
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "user",
            "parent_comment",
            "content",
            "created_at",
            "target_type",
            "target_id",
            "statistics",
        ]
        read_only_fields = ["id", "created_at", "is_deleted"]

    def get_target_type(self, obj) -> str:
        return obj.content_type.model

    def get_target_id(self, obj) -> int:
        return obj.object_id

    def get_statistics(self, obj) -> serializers.DictField:
        from feed.services.comment import CommentService
        request = self.context.get("request", None)
        return CommentService.get_comment_statistics(obj, request.user)
    
    
class CommentDisplaySerializerNoReplies(serializers.ModelSerializer):
    """Detailed view for a comment without nested replies."""

    user = UserMinimalSerializer(read_only=True)
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "user",
            "parent_comment",
            "content",
            "created_at",
            "target_type",
            "target_id",
            "statistics",
        ]
        read_only_fields = ["id", "created_at", "is_deleted"]

    def get_target_type(self, obj) -> str:
        return obj.content_type.model

    def get_target_id(self, obj) -> int:
        return obj.object_id

    def get_statistics(self, obj) -> serializers.DictField:
        from feed.services.comment import CommentService
        request = self.context.get("request", None)
        return CommentService.get_comment_statistics(obj, request.user)
    
    
    
    
    
    
    
    
class CommentDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a comment with nested replies."""

    user = UserMinimalSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()
    

    class Meta:
        model = Comment
        fields = [
            "id",
            "user",
            "parent_comment",
            "content",
            "created_at",
            "replies",
            "target_type",
            "target_id",
            "statistics",
        ]
        read_only_fields = ["id", "created_at", "is_deleted"]

    def get_target_type(self, obj) -> str:
        return obj.content_type.model

    def get_target_id(self, obj) -> int:
        return obj.object_id

    def get_replies(self, obj) -> CommentDisplaySerializerNoReplies(many=True):  # type: ignore
        from feed.services.comment import CommentService
        replies = CommentService.get_comment_replies(obj, limit=10)
        return CommentDisplaySerializerNoReplies(
            replies, many=True, context=self.context
        ).data
    
    def get_statistics(self, obj) -> serializers.DictField:
        from feed.services.comment import CommentService
        request = self.context.get("request", None)
        return CommentService.get_comment_statistics(obj, request.user)
    
    
class PostFeedSerializer(serializers.ModelSerializer):
    """Optimized for feed listings."""

    user = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer(read_only=True, allow_null=True)
    shared_post = serializers.SerializerMethodField()
    preview = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()
    media = MediaDisplaySerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = [
            "id",
            "user",
            "shared_post",
            "group",
            "content",
            "privacy",
            "post_type",
            "media",
            "preview",
            "created_at",
            "statistics",
        ]

    def get_preview(self, obj) -> str:
        if obj.content:
            return obj.content[:150] + ("..." if len(obj.content) > 150 else "")
        return ""

    def get_shared_post(self, obj) -> serializers.DictField:
        from feed.serializers.post import PostMinimalSerializer
        if obj.shared_post:
            return PostMinimalSerializer(obj.shared_post, context=self.context).data
        return None

    def get_statistics(self, obj) -> serializers.DictField:
        from feed.services.post import PostService
        return PostService.get_post_statistics(serializer=self, obj=obj)