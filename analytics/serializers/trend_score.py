from rest_framework import serializers
from analytics.models.trend_score import ObjectTrendScore
from analytics.services.trend_score import TrendScoreService


class TrendScoreStatisticsSerializer(serializers.Serializer):
    """Aggregated statistics for trend scores across objects."""
    average_score = serializers.FloatField()
    highest_score = serializers.FloatField()
    lowest_score = serializers.FloatField()


class TrendScoreMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for trend scores."""
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    class Meta:
        model = ObjectTrendScore
        fields = [
            "id",
            "score",
            "calculated_at",
            "target_type",
            "target_id",
        ]
        read_only_fields = fields

    def get_target_type(self, obj) -> str:
        return obj.content_type.model

    def get_target_id(self, obj) -> int:
        return obj.object_id


class TrendScoreDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a trend score record with stats."""
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = ObjectTrendScore
        fields = [
            "id",
            "score",
            "calculated_at",
            "target_type",
            "target_id",
            "statistics",
        ]
        read_only_fields = ["id", "calculated_at"]

    def get_target_type(self, obj) -> str:
        return obj.content_type.model

    def get_target_id(self, obj) -> int:
        return obj.object_id

    def get_statistics(self, obj) -> TrendScoreStatisticsSerializer:
        stats = {
            "average_score": TrendScoreService.get_average_score(),
            "highest_score": TrendScoreService.get_highest_score(),
            "lowest_score": TrendScoreService.get_lowest_score(),
        }
        return TrendScoreStatisticsSerializer(stats).data


class TrendScoreCreateSerializer(serializers.Serializer):
    """Serializer for creating/updating a trend score for an object."""
    target_type = serializers.CharField(write_only=True)
    target_id = serializers.IntegerField(write_only=True)

    def create(self, validated_data):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        target_type = validated_data["target_type"]
        target_id = validated_data["target_id"]

        from django.contrib.contenttypes.models import ContentType
        try:
            ct = ContentType.objects.get(model=target_type)
            model_class = ct.model_class()
            content_object = model_class.objects.get(pk=target_id)
        except Exception:
            raise serializers.ValidationError({"target": "Invalid target object"})

        # Calculate and persist score
        return TrendScoreService.calculate_score(content_object)
