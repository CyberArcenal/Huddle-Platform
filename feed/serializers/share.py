from asyncio import Event
from typing import Dict, Any, Optional

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from events.serializers.event import EventListSerializer
from feed.models import Share
from feed.models.post import POST_PRIVACY_TYPES, Post
from feed.models.reel import Reel
from feed.serializers.base import (
    PostStatsSerializers,
    ReactionCountSerializer,
    ShareContentObjectDetail,
)
from feed.serializers.comment import CommentDisplaySerializer
from feed.serializers.post import PostFeedSerializer
from feed.serializers.reel import ReelDisplaySerializer
from feed.services.comment import CommentService
from feed.services.reaction import ReactionService
from feed.services.share import ShareService
from groups.models.group import Group
from groups.serializers.group import GroupMinimalSerializer
from stories.models.story import Story
from stories.serializers.base import StorySerializer
from users.models.user import UserImage
from users.serializers.user import UserMinimalSerializer
from users.serializers.user_image import UserImageDisplaySerializer


class ShareMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for shares."""

    user = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer(read_only=True)
    content_preview = serializers.SerializerMethodField()

    class Meta:
        model = Share
        fields = [
            "id",
            "user",
            "group",
            "caption",
            "content_preview",
            "privacy",
            "created_at",
        ]
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
    privacy = serializers.ChoiceField(choices=POST_PRIVACY_TYPES, default="public")
    group = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Share
        fields = ["content_type", "object_id", "caption", "privacy", "group"]

    def validate(self, data):
        content_type_str = data.get("content_type")
        object_id = data.get("object_id")

        # Resolve content type
        try:
            app_label, model = content_type_str.split(".")
            content_type = ContentType.objects.get(app_label=app_label, model=model)
        except (ValueError, ContentType.DoesNotExist):
            raise serializers.ValidationError(
                {
                    "content_type": f"Invalid content type '{content_type_str}'. Use format 'app_label.model'."
                }
            )

        # Get the actual object
        try:
            obj = content_type.get_object_for_this_type(id=object_id)
        except content_type.model_class().DoesNotExist:
            raise serializers.ValidationError({"object_id": "Object not found."})

        # Optional: Check if the object is shareable (e.g., not deleted)
        if hasattr(obj, "is_deleted") and obj.is_deleted:
            raise serializers.ValidationError("Cannot share a deleted object.")

        data["content_object"] = obj
        return data

    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        content_object = validated_data.pop("content_object")
        try:
            share = ShareService.create_share(
                user=request.user,
                content_object=content_object,
                caption=validated_data.get("caption", ""),
                privacy=validated_data.get("privacy", "public"),
                group=validated_data.get("group", None),
            )
            return share
        except ValidationError as e:
            raise serializers.ValidationError(str(e))


class ShareDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a share."""

    user = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer(read_only=True)
    content_object_detail = serializers.SerializerMethodField()
    content_object_data = serializers.SerializerMethodField()
    share_count = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Share
        fields = [
            "id",
            "user",
            "group",
            "content_object_detail",
            "content_object_data",
            "caption",
            "privacy",
            "is_deleted",
            "created_at",
            "updated_at",
            "share_count",
            "statistics",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "is_deleted"]

    def get_content_object_detail(self, obj) -> ShareContentObjectDetail:
        if not obj.content_object:
            return None
        return {
            "type": obj.content_type.model,
            "id": obj.object_id,
            "representation": str(obj.content_object),
        }

    def get_content_object_data(self, obj) -> serializers.DictField:
        content_object = getattr(obj, "content_object", None)
        if not content_object:
            return None

        # Import Post here or at module top
        if isinstance(content_object, Post):
            return PostFeedSerializer(content_object, context=self.context).data

        if isinstance(content_object, Event):
            return EventListSerializer(content_object, context=self.context).data

        if isinstance(content_object, Story):
            return StorySerializer(content_object, context=self.context).data

        if isinstance(content_object, Reel):
            return ReelDisplaySerializer(content_object, context=self.context).data
        # Example: user image or story
        if isinstance(content_object, UserImage):
            return UserImageDisplaySerializer(content_object, context=self.context).data

        # Fallback: minimal representation
        model_cls = content_object.__class__
        model_name = getattr(model_cls._meta, "model_name", model_cls.__name__).lower()
        return {
            "type": model_name,
            "id": getattr(content_object, "id", getattr(obj, "object_id", None)),
            "representation": str(content_object),
        }

    def get_share_count(self, obj) -> int:
        return ShareService.get_share_count(obj.content_object)

    def get_statistics(self, obj) -> PostStatsSerializers:
        from feed.services.post import PostService

        return PostService.get_post_statistics(serializer=self, obj=obj)


class ShareFeedSerializer(serializers.ModelSerializer):
    """Optimized for feed listings (similar to PostFeedSerializer)."""

    user = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer(read_only=True)
    content_preview = serializers.SerializerMethodField()
    content_object_detail = serializers.SerializerMethodField()
    content_object_data = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Share
        fields = [
            "id",
            "user",
            "group",
            "caption",
            "content_preview",
            "content_object_detail",
            "content_object_data",
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

    def get_content_object_detail(self, obj) -> ShareContentObjectDetail:
        if not obj.content_object:
            return None
        return {
            "type": obj.content_type.model,
            "id": obj.object_id,
            "representation": str(obj.content_object),
        }

    def get_content_object_data(self, obj) -> serializers.DictField:
        content_object = getattr(obj, "content_object", None)
        if not content_object:
            return None

        # Import Post here or at module top
        if isinstance(content_object, Post):
            return PostFeedSerializer(content_object, context=self.context).data

        if isinstance(content_object, Event):
            return EventListSerializer(content_object, context=self.context).data

        if isinstance(content_object, Story):
            return StorySerializer(content_object, context=self.context).data

        if isinstance(content_object, Reel):
            return ReelDisplaySerializer(content_object, context=self.context).data
        # Example: user image or story
        if isinstance(content_object, UserImage):
            return UserImageDisplaySerializer(content_object, context=self.context).data

        # Fallback: minimal representation
        model_cls = content_object.__class__
        model_name = getattr(model_cls._meta, "model_name", model_cls.__name__).lower()
        return {
            "type": model_name,
            "id": getattr(content_object, "id", getattr(obj, "object_id", None)),
            "representation": str(content_object),
        }

    def get_statistics(self, obj) -> PostStatsSerializers:
        from feed.services.post import PostService

        return PostService.get_post_statistics(serializer=self, obj=obj)
