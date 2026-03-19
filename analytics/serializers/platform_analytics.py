from rest_framework import serializers

from analytics.models.platform_analytics import PlatformAnalytics


class PlatformAnalyticsMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for platform analytics (daily snapshots)."""
    class Meta:
        model = PlatformAnalytics
        fields = ['id', 'date', 'total_users', 'active_users', 'new_posts']
        read_only_fields = fields


class PlatformAnalyticsCreateSerializer(serializers.ModelSerializer):
    """Used when creating a new platform analytics record."""
    class Meta:
        model = PlatformAnalytics
        fields = [
            'date', 'total_users', 'active_users', 'new_posts',
            'new_groups', 'total_messages'
        ]


class PlatformAnalyticsDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single platform analytics entry."""
    class Meta:
        model = PlatformAnalytics
        fields = '__all__'
        read_only_fields = ['id', 'date']   # date might be auto-set