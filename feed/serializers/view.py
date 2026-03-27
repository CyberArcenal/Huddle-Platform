from rest_framework import serializers
from feed.models.view import ObjectView
from feed.services.view import ViewService
from django.contrib.contenttypes.models import ContentType

from users.serializers.user.minimal import UserMinimalSerializer


class ViewStatisticsSerializer(serializers.Serializer):
    """Aggregated statistics for views on a content object."""
    view_count = serializers.IntegerField()
    unique_viewers = serializers.IntegerField()
    total_duration = serializers.IntegerField()
    average_duration = serializers.FloatField()


class ViewCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a view record on any content object."""

    target_type = serializers.CharField(write_only=True)
    target_id = serializers.IntegerField(write_only=True)
    duration_seconds = serializers.IntegerField(write_only=True, required=False, default=0)

    class Meta:
        model = ObjectView
        fields = ["target_type", "target_id", "duration_seconds"]

    def create(self, validated_data):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        user = request.user if request.user.is_authenticated else None
        target_type = validated_data["target_type"]
        target_id = validated_data["target_id"]
        duration = validated_data.get("duration_seconds", 0)

        try:
            ct = ContentType.objects.get(model=target_type)
            model_class = ct.model_class()
            content_object = model_class.objects.get(pk=target_id)
        except Exception:
            raise serializers.ValidationError({"target": "Invalid target object"})

        # Use the service layer to add the view
        return ViewService.add_view(user=user, obj=content_object, duration=duration)

class ViewMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for individual view records."""
    user = UserMinimalSerializer(read_only=True)
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    class Meta:
        model = ObjectView
        fields = [
            "id",
            "user",
            "viewed_at",
            "duration_seconds",
            "target_type",
            "target_id",
        ]
        read_only_fields = fields

    def get_target_type(self, obj) -> str:
        return obj.content_type.model

    def get_target_id(self, obj) -> int:
        return obj.object_id


class ViewDisplaySerializer(serializers.ModelSerializer):
    """Detailed view record with statistics for the target object."""
    user = UserMinimalSerializer(read_only=True)
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = ObjectView
        fields = [
            "id",
            "user",
            "viewed_at",
            "duration_seconds",
            "target_type",
            "target_id",
            "statistics",
        ]
        read_only_fields = ["id", "viewed_at"]

    def get_target_type(self, obj) -> str:
        return obj.content_type.model

    def get_target_id(self, obj) -> int:
        return obj.object_id

    def get_statistics(self, obj) -> ViewStatisticsSerializer:
        """Return aggregated stats for the target object."""
        stats = {
            "view_count": ViewService.get_view_count(obj.content_object),
            "unique_viewers": ViewService.get_unique_viewers(obj.content_object),
            "total_duration": ViewService.get_total_duration(obj.content_object),
            "average_duration": ViewService.get_average_duration(obj.content_object),
        }
        return ViewStatisticsSerializer(stats).data
    
    def has_viewed(obj, user):
        pass
