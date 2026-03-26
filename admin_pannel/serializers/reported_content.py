from rest_framework import serializers
from admin_pannel.models.reported_content import ReportedContent
from admin_pannel.services.reported_content import ReportedContentService
from users.serializers.user import UserMinimalSerializer


class ReportedContentMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for reported content."""
    reporter = serializers.StringRelatedField(read_only=True)
    content_type_display = serializers.CharField(source="get_content_type_display", read_only=True)

    class Meta:
        model = ReportedContent
        fields = [
            "id",
            "reporter",
            "content_type",
            "content_type_display",
            "object_id",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class ReportedContentCreateSerializer(serializers.Serializer):
    """Serializer for creating a new report (delegates to service)."""
    content_type = serializers.CharField()
    object_id = serializers.IntegerField()
    reason = serializers.CharField()

    def create(self, validated_data):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})
        user = request.user
        return ReportedContentService.report_content(
            reporter=user,
            content_type=validated_data["content_type"],
            object_id=validated_data["object_id"],
            reason=validated_data["reason"],
        )


class ReportedContentDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single report."""
    reporter = UserMinimalSerializer(read_only=True)
    content_type_display = serializers.CharField(source="get_content_type_display", read_only=True)

    class Meta:
        model = ReportedContent
        fields = [
            "id",
            "reporter",
            "content_type",
            "content_type_display",
            "object_id",
            "reason",
            "status",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = ["id", "created_at", "resolved_at"]


class ReportedContentStatisticsSerializer(serializers.Serializer):
    """Aggregated statistics for reports."""
    period_days = serializers.IntegerField()
    total_reports = serializers.IntegerField()
    pending_reports = serializers.IntegerField()
    resolution_rate = serializers.FloatField()
    avg_resolution_hours = serializers.FloatField(allow_null=True)
    type_breakdown = serializers.ListField(child=serializers.DictField())
    status_breakdown = serializers.ListField(child=serializers.DictField())
    top_reporters = serializers.ListField(child=serializers.DictField())
    most_reported_objects = serializers.ListField(child=serializers.DictField())
