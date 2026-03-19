from rest_framework import serializers
from analytics.models.user_analytics import UserAnalytics
from users.models import User


class UserAnalyticsMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for user analytics (daily snapshots)."""
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = UserAnalytics
        fields = ['id', 'user', 'username', 'date', 'posts_count', 'likes_received']
        read_only_fields = fields


class UserAnalyticsCreateSerializer(serializers.ModelSerializer):
    """Used when creating a new user analytics record."""
    class Meta:
        model = UserAnalytics
        fields = [
            'user', 'date', 'posts_count', 'likes_received', 'comments_received',
            'new_followers', 'stories_posted'
        ]


class UserAnalyticsDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single user analytics entry."""
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = UserAnalytics
        fields = '__all__'
        read_only_fields = ['id', 'date']