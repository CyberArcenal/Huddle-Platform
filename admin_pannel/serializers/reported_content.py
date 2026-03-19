from rest_framework import serializers
from admin_pannel.models.reported_content import ReportedContent
from users.serializers.user import UserMinimalSerializer


class ReportedContentMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for reported content."""
    reporter = serializers.StringRelatedField(read_only=True)
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)

    class Meta:
        model = ReportedContent
        fields = ['id', 'reporter', 'content_type', 'content_type_display',
                  'object_id', 'status', 'created_at']
        read_only_fields = fields


class ReportedContentCreateSerializer(serializers.ModelSerializer):
    """Used when creating a new report."""
    class Meta:
        model = ReportedContent
        fields = ['reporter', 'content_type', 'object_id', 'reason']


class ReportedContentDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single report."""
    reporter = UserMinimalSerializer(read_only=True)
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)

    class Meta:
        model = ReportedContent
        fields = '__all__'
        read_only_fields = ['created_at', 'resolved_at']