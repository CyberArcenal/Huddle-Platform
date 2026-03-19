from typing import Dict, Any, Optional

from django.core.exceptions import ValidationError
from rest_framework import serializers

from feed.models.base import Comment, Post, User
from feed.models.reaction import ReactionType
from feed.serializers.base import ReactionCountSerializer
from feed.services.comment import CommentService
from feed.services.reaction import ReactionService
from users.serializers.user import UserMinimalSerializer


from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType

from feed.models.base import Comment
from feed.services.comment import CommentService
from users.serializers.user import UserMinimalSerializer


class CommentMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for comments."""

    user = UserMinimalSerializer(read_only=True)
    content_preview = serializers.SerializerMethodField()
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "user", "content_preview", "created_at", "target_type", "target_id"]
        read_only_fields = fields

    def get_content_preview(self, obj) -> str:
        return (
            obj.content[:100] + ("..." if len(obj.content) > 100 else "")
            if obj.content
            else ""
        )

    def get_target_type(self, obj):
        return obj.content_type.model

    def get_target_id(self, obj):
        return obj.object_id


class CommentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a comment on any content object."""

    target_type = serializers.CharField(write_only=True)
    target_id = serializers.IntegerField(write_only=True)
    parent_comment_id = serializers.PrimaryKeyRelatedField(
        queryset=Comment.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
        source="parent_comment"
    )

    class Meta:
        model = Comment
        fields = ["target_type", "target_id", "parent_comment_id", "content"]

    def create(self, validated_data):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        user = request.user
        target_type = validated_data["target_type"]
        target_id = validated_data["target_id"]

        try:
            ct = ContentType.objects.get(model=target_type)
            model_class = ct.model_class()
            content_object = model_class.objects.get(pk=target_id)
        except Exception:
            raise serializers.ValidationError({"target": "Invalid target object"})

        return CommentService.create_comment(
            user=user,
            content_object=content_object,
            content=validated_data["content"],
            parent_comment=validated_data.get("parent_comment"),
        )

    def update(self, instance, validated_data):
        return CommentService.update_comment(
            comment=instance,
            new_content=validated_data.get("content", instance.content),
        )

class CommentDisplaySerializerNoReplies(serializers.ModelSerializer):
    """Detailed view for a comment without nested replies."""

    user = UserMinimalSerializer(read_only=True)

    like_count = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    reaction_counts = serializers.SerializerMethodField()
    user_reaction = serializers.SerializerMethodField()
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

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
            "like_count",
            "liked",
            "reaction_counts",
            "user_reaction",
        ]
        read_only_fields = ["id", "created_at", "is_deleted"]

    def get_target_type(self, obj):
        return obj.content_type.model

    def get_target_id(self, obj):
        return obj.object_id

    def get_reaction_counts(self, obj) -> ReactionCountSerializer:
        return ReactionService.get_reaction_counts("comment", obj.id)

    def get_user_reaction(self, obj) -> Optional[ReactionType]:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.get_user_reaction(request.user, "comment", obj.id)
        return None

    def get_like_count(self, obj) -> int:
        return ReactionService.get_like_count("comment", obj.id)

    def get_liked(self, obj) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.has_liked(
                user=request.user, content_type="comment", object_id=obj.id
            )
        return False


class CommentDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a comment with nested replies."""

    user = UserMinimalSerializer(read_only=True)
    replies = serializers.SerializerMethodField()

    like_count = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    reaction_counts = serializers.SerializerMethodField()
    user_reaction = serializers.SerializerMethodField()
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

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
            "like_count",
            "liked",
            "reaction_counts",
            "user_reaction",
        ]
        read_only_fields = ["id", "created_at", "is_deleted"]

    def get_target_type(self, obj):
        return obj.content_type.model

    def get_target_id(self, obj):
        return obj.object_id

    def get_replies(self, obj) -> CommentDisplaySerializerNoReplies:
        replies = CommentService.get_comment_replies(obj, limit=10)
        return CommentDisplaySerializerNoReplies(replies, many=True, context=self.context).data

    def get_reaction_counts(self, obj) -> ReactionCountSerializer:
        return ReactionService.get_reaction_counts("comment", obj.id)

    def get_user_reaction(self, obj) -> Optional[ReactionType]:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.get_user_reaction(request.user, "comment", obj.id)
        return None

    def get_like_count(self, obj) -> int:
        return ReactionService.get_like_count("comment", obj.id)

    def get_liked(self, obj) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.has_liked(
                user=request.user, content_type="comment", object_id=obj.id
            )
        return False
