from rest_framework import serializers
from events.models.event_analytics import EventAnalytics
from events.serializers import EventListSerializer  # adjust import path if needed


class EventAnalyticsSerializer(serializers.ModelSerializer):
    event_title = serializers.CharField(source='event.title', read_only=True)

    class Meta:
        model = EventAnalytics
        fields = '__all__'


class EventAnalyticsSummarySerializer(serializers.Serializer):
    event_id = serializers.IntegerField()
    period_days = serializers.IntegerField()
    total_rsvp_changes = serializers.IntegerField()
    avg_changes_per_day = serializers.FloatField()
    current_rsvp_counts = serializers.DictField(child=serializers.IntegerField())
    daily_breakdown = serializers.ListField(child=serializers.DictField())