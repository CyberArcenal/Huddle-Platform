from rest_framework import serializers
from feed.services.bookmark import BookmarkService
from users.serializers.user import UserMinimalSerializer
from feed.models.bookmark import ObjectBookmark
from django.contrib.contenttypes.models import ContentType


class BookmarkStatisticsSerializer(serializers.Serializer):
    """Aggregated statistics for bookmarks on a content object."""
    bookmark_count = serializers.IntegerField()
    has_bookmarked = serializers.BooleanField()


class BookmarkMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for individual bookmark records."""
    user = UserMinimalSerializer(read_only=True)
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    class Meta:
        model = ObjectBookmark
        fields = [
            "id",
            "user",
            "created_at",
            "target_type",
            "target_id",
        ]
        read_only_fields = fields

    def get_target_type(self, obj) -> str:
        return obj.content_type.model

    def get_target_id(self, obj) -> int:
        return obj.object_id


class BookmarkDisplaySerializer(serializers.ModelSerializer):
    """Detailed bookmark record with statistics for the target object."""
    user = UserMinimalSerializer(read_only=True)
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = ObjectBookmark
        fields = [
            "id",
            "user",
            "created_at",
            "target_type",
            "target_id",
            "statistics",
        ]
        read_only_fields = ["id", "created_at"]

    def get_target_type(self, obj) -> str:
        return obj.content_type.model

    def get_target_id(self, obj) -> int:
        return obj.object_id

    def get_statistics(self, obj) -> BookmarkStatisticsSerializer:
        request = self.context.get("request", None)
        user = request.user if request and request.user.is_authenticated else None
        stats = {
            "bookmark_count": BookmarkService.get_bookmark_count(obj.content_object),
            "has_bookmarked": BookmarkService.has_bookmarked(user, obj.content_object) if user else False,
        }
        return BookmarkStatisticsSerializer(stats).data


class BookmarkCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a bookmark on any content object."""

    target_type = serializers.CharField(write_only=True)
    target_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ObjectBookmark
        fields = ["target_type", "target_id"]

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

        return BookmarkService.add_bookmark(user=user, obj=content_object)
