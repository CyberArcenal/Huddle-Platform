from typing import Dict, Any, Optional

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from feed.models import Share
from feed.serializers.base import ReactionCountSerializer, ShareContentObjectData
from feed.serializers.comment import CommentDisplaySerializer
from feed.services.comment import CommentService
from feed.services.reaction import ReactionService
from feed.services.share import ShareService
from users.serializers.user import UserMinimalSerializer


class ShareStatsSerializer(serializers.Serializer):
    """Statistics for a Share object."""

    comment_count = serializers.IntegerField(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    reaction_count = ReactionCountSerializer()
    comments = CommentDisplaySerializer(many=True, read_only=True)
    liked = serializers.BooleanField(read_only=True)
    
    

class ShareMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for shares."""

    user = UserMinimalSerializer(read_only=True)
    content_preview = serializers.SerializerMethodField()

    class Meta:
        model = Share
        fields = ["id", "user", "caption", "content_preview", "privacy", "created_at"]
        read_only_fields = fields

    def get_content_preview(self, obj) -> str:
        return (
            obj.caption[:100] + ("..." if len(obj.caption) > 100 else "")
            if obj.caption
            else ""
        )


class ShareCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a share."""

    content_type = serializers.CharField(write_only=True)
    object_id = serializers.IntegerField(write_only=True)
    caption = serializers.CharField(required=False, allow_blank=True)
    privacy = serializers.ChoiceField(
        choices=Share._meta.get_field('privacy').choices,
        default='public'
    )

    class Meta:
        model = Share
        fields = ["content_type", "object_id", "caption", "privacy"]

    def validate(self, data):
        content_type_str = data.get("content_type")
        object_id = data.get("object_id")

        # Resolve content type
        try:
            app_label, model = content_type_str.split('.')
            content_type = ContentType.objects.get(app_label=app_label, model=model)
        except (ValueError, ContentType.DoesNotExist):
            raise serializers.ValidationError(
                {"content_type": f"Invalid content type '{content_type_str}'. Use format 'app_label.model'."}
            )

        # Get the actual object
        try:
            obj = content_type.get_object_for_this_type(id=object_id)
        except content_type.model_class().DoesNotExist:
            raise serializers.ValidationError({"object_id": "Object not found."})

        # Optional: Check if the object is shareable (e.g., not deleted)
        if hasattr(obj, 'is_deleted') and obj.is_deleted:
            raise serializers.ValidationError("Cannot share a deleted object.")

        data['content_object'] = obj
        return data

    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        content_object = validated_data.pop('content_object')
        try:
            share = ShareService.create_share(
                user=request.user,
                content_object=content_object,
                caption=validated_data.get('caption', ''),
                privacy=validated_data.get('privacy', 'public')
            )
            return share
        except ValidationError as e:
            raise serializers.ValidationError(str(e))


class ShareDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a share."""

    user = UserMinimalSerializer(read_only=True)
    content_object = serializers.SerializerMethodField()
    share_count = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Share
        fields = [
            "id",
            "user",
            "content_object",
            "caption",
            "privacy",
            "is_deleted",
            "created_at",
            "updated_at",
            "share_count",
            "statistics",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "is_deleted"]

    def get_content_object(self, obj) -> ShareContentObjectData:
        if not obj.content_object:
            return None
        return {
            "type": obj.content_type.model,
            "id": obj.object_id,
            "representation": str(obj.content_object),
        }

    def get_share_count(self, obj) -> int:
        return ShareService.get_share_count(obj.content_object)

    def get_statistics(self, obj) -> ShareStatsSerializer:
        request = self.context.get("request")
        return {
            "comment_count": CommentService.get_comment_count(obj),
            "like_count": ReactionService.get_like_count("share", obj.id),
            "reaction_count": ReactionService.get_reaction_counts("share", obj.id),
            "comments": CommentDisplaySerializer(
                CommentService.get_comments_for_object(obj, limit=5),
                many=True,
                context=self.context,
            ).data,
            "liked": (
                ReactionService.has_liked(
                    user=request.user, content_type="share", object_id=obj.id
                )
                if request and request.user.is_authenticated
                else False
            ),
        }


class ShareFeedSerializer(serializers.ModelSerializer):
    """Optimized for feed listings (similar to PostFeedSerializer)."""

    user = UserMinimalSerializer(read_only=True)
    content_preview = serializers.SerializerMethodField()
    content_object = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Share
        fields = [
            "id",
            "user",
            "caption",
            "content_preview",
            "content_object",
            "privacy",
            "created_at",
            "statistics",
        ]

    def get_content_preview(self, obj) -> str:
        return (
            obj.caption[:150] + ("..." if len(obj.caption) > 150 else "")
            if obj.caption
            else ""
        )

    def get_content_object(self, obj) -> ShareContentObjectData:
        if not obj.content_object:
            return None
        return {
            "type": obj.content_type.model,
            "id": obj.object_id,
            "representation": str(obj.content_object),
        }

    def get_statistics(self, obj) -> ShareStatsSerializer:
        request = self.context.get("request")
        return {
            "comment_count": CommentService.get_comment_count(obj),
            "like_count": ReactionService.get_like_count("share", obj.id),
            "reaction_count": ReactionService.get_reaction_counts("share", obj.id),
            "comments": CommentDisplaySerializer(
                CommentService.get_comments_for_object(obj, limit=3),
                many=True,
                context=self.context,
            ).data,
            "liked": (
                ReactionService.has_liked(
                    user=request.user, content_type="share", object_id=obj.id
                )
                if request and request.user.is_authenticated
                else False
            ),
        }