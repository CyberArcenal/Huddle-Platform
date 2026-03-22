# serializers/activity_serializer.py
from rest_framework import serializers
from django.utils import timezone
from django.db.models import Count, Q
from typing import Dict, Any, List, Optional

from users.serializers.user import UserListSerializer

from ..models import UserActivity, SecurityLog, LoginSession


class UserActivitySerializer(serializers.ModelSerializer):
    """Serializer for user activity logs"""

    user = UserListSerializer(read_only=True)
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    formatted_time = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = UserActivity
        fields = [
            "id",
            "user",
            "action",
            "action_display",
            "description",
            "ip_address",
            "user_agent",
            "timestamp",
            "formatted_time",
            "time_ago",
            "location",
            "metadata",
        ]
        read_only_fields = fields

    def get_formatted_time(self, obj) -> str:
        """Format timestamp to readable string"""
        return obj.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    def get_time_ago(self, obj) -> str:
        """Get human-readable time difference"""
        now = timezone.now()
        delta = now - obj.timestamp

        if delta.days > 365:
            years = delta.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"


class ActivitySummarySerializer(serializers.Serializer):
    """Serializer for user activity summary/statistics"""

    total_activities = serializers.IntegerField()
    last_activity = serializers.DateTimeField()
    activities_by_type = serializers.DictField()
    activities_today = serializers.IntegerField()
    activities_this_week = serializers.IntegerField()

    def to_representation(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        """Format activity summary"""
        return {
            "total_activities": instance.get("total_activities", 0),
            "last_activity": instance.get("last_activity"),
            "activity_types": instance.get("activities_by_type", {}),
            "today": instance.get("activities_today", 0),
            "this_week": instance.get("activities_this_week", 0),
        }


# ===== Response serializers for drf-spectacular =====


class ActivitySummaryResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    summary = ActivitySummarySerializer()


class LogActivityResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    activity = UserActivitySerializer()
