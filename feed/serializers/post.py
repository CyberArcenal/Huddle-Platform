import logging
from typing import Dict, Any, List, Optional

from django.core.exceptions import ValidationError
from rest_framework import serializers

from feed.models.base import Post
from feed.models.reaction import ReactionType
from feed.serializers.base import (
    PostStatisticsSerializer,
    PostStatsSerializers,
    ReactionCountSerializer,
)
from feed.services.comment import CommentService
from feed.services.reaction import ReactionService

from groups.models.group import Group
from groups.serializers.group import GroupMinimalSerializer
from users.serializers.user import UserMinimalSerializer, UserMinimalSerializer

from .comment import CommentDisplaySerializer
from .post_media import PostMediaDisplaySerializer, PostMediaCreateSerializer

logger = logging.getLogger(__name__)


class PostMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for posts."""

    user = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer(read_only=True)
    preview = serializers.SerializerMethodField()
    media_preview = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "user",
            "preview",
            "post_type",
            "privacy",
            "group",
            "created_at",
            "media_preview",
        ]
        read_only_fields = fields

    def get_preview(self, obj) -> str:
        return (
            obj.content[:150] + ("..." if len(obj.content) > 150 else "")
            if obj.content
            else ""
        )

    def get_media_preview(self, obj) -> PostMediaDisplaySerializer:
        first_media = obj.media.first()
        if first_media:
            return PostMediaDisplaySerializer(first_media, context=self.context).data
        return None


class PostCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new post."""

    content = serializers.CharField(required=False, allow_blank=True)
    media_files = serializers.ListField(
        child=serializers.FileField(), write_only=True, required=False, allow_empty=True
    )
    group = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Post
        fields = ["content", "group", "post_type", "privacy", "media_files"]

    def validate(self, data):
        post_type = data.get("post_type", "text")
        media_files = data.get("media_files", [])

        if post_type in ["image", "video"] and not media_files:
            raise serializers.ValidationError(
                {
                    "media_files": f"{post_type.capitalize()} posts require at least one media file."
                }
            )
        if post_type == "text" and media_files:
            raise serializers.ValidationError(
                {"media_files": "Text posts cannot have media."}
            )
        if post_type == "text" and not data.get("content", "").strip():
            raise serializers.ValidationError(
                {"content": "Text posts require content."}
            )
        return data

    def create(self, validated_data):
        from feed.services.post import PostService

        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError("Request object required.")

        try:
            post = PostService.create_post(
                user=request.user,
                content=validated_data.get("content", ""),
                post_type=validated_data.get("post_type", "text"),
                media_files=validated_data.get("media_files", []),
                privacy=validated_data.get("privacy", "followers"),
            )
            return post
        except ValidationError as e:
            raise serializers.ValidationError(str(e))

    def update(self, instance, validated_data):
        from feed.services.post import PostService

        try:
            updated_post = PostService.update_post(
                post=instance, update_data=validated_data
            )
            return updated_post
        except ValidationError as e:
            raise serializers.ValidationError(str(e))


class PostDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single post."""

    user = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer(read_only=True, allow_null=True)
    shared_post = serializers.SerializerMethodField()
    media = PostMediaDisplaySerializer(many=True, read_only=True)
    comments = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    reaction_counts = serializers.SerializerMethodField()
    user_reaction = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "user",
            "shared_post",
            "group",
            "content",
            "post_type",
            "media",
            "privacy",
            "is_deleted",
            "created_at",
            "updated_at",
            "comments",
            "comment_count",
            "like_count",
            "liked",
            "reaction_counts",
            "user_reaction",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "is_deleted"]
    
    def get_shared_post(self, obj) -> PostMinimalSerializer:
        if obj.shared_post:
            return PostMinimalSerializer(obj.shared_post, context=self.context).data
        return None

    def get_comments(self, obj) -> CommentDisplaySerializer(many=True):  # type: ignore
        comments = CommentService.get_comments_for_object(
            content_object=obj, include_replies=False, limit=10
        )
        return CommentDisplaySerializer(comments, many=True, context=self.context).data

    def get_comment_count(self, obj) -> int:
        return CommentService.get_comment_count(obj)

    def get_reaction_counts(self, obj) -> ReactionCountSerializer:
        return ReactionService.get_reaction_counts(obj, obj.id)

    def get_user_reaction(self, obj) -> Optional[ReactionType]:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.get_user_reaction(request.user, obj, obj.id)
        return None

    def get_like_count(self, obj) -> int:
        return ReactionService.get_like_count(obj, obj.id)

    def get_liked(self, obj) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.has_liked(
                user=request.user, content_type=obj, object_id=obj.id
            )
        return False


class PostDetailSerializer(PostDisplaySerializer):
    """Extended view with additional statistics."""

    statistics = serializers.SerializerMethodField()

    class Meta(PostDisplaySerializer.Meta):
        fields = PostDisplaySerializer.Meta.fields + ["statistics"]

    def get_statistics(self, obj) -> PostStatisticsSerializer:
        from feed.services.post import PostService

        return PostService.get_post_statistics(obj)


class PostFeedSerializer(serializers.ModelSerializer):
    """Optimized for feed listings."""

    user = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer(read_only=True, allow_null=True)
    shared_post = serializers.SerializerMethodField()
    preview = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()
    media = PostMediaDisplaySerializer(many=True, read_only=True)

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
    
    def get_shared_post(self, obj) -> PostMinimalSerializer:
        if obj.shared_post:
            return PostMinimalSerializer(obj.shared_post, context=self.context).data
        return None

    def get_statistics(self, obj) -> PostStatsSerializers:
        request = self.context.get("request")
        return {
            "comment_count": CommentService.get_comment_count(obj),
            "like_count": ReactionService.get_like_count(obj, obj.id),
            "reaction_count": ReactionService.get_reaction_counts(obj, obj.id),
            "comments": CommentDisplaySerializer(
                CommentService.get_comments_for_object(obj, limit=10),
                many=True,
                context=self.context,
            ).data,
            "liked": (
                ReactionService.has_liked(
                    user=request.user, content_type=obj, object_id=obj.id
                )
                if request and request.user.is_authenticated
                else False
            ),
        }
    
    
