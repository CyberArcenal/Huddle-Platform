from rest_framework import serializers
from notifications.models import Notification
from users.serializers.user import UserMinimalSerializer


class NotificationSerializer(serializers.ModelSerializer):
    actor_details = UserMinimalSerializer(source='actor', read_only=True)
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'actor', 'actor_details', 'notification_type',
            'message', 'is_read', 'related_id', 'related_model', 'created_at',
            'time_ago'
        ]
        read_only_fields = ['user', 'actor', 'created_at']

    def get_time_ago(self, obj):
        from django.utils import timezone
        delta = timezone.now() - obj.created_at
        if delta.days > 0:
            return f"{delta.days} day(s) ago"
        elif delta.seconds // 3600 > 0:
            return f"{delta.seconds // 3600} hour(s) ago"
        elif delta.seconds // 60 > 0:
            return f"{delta.seconds // 60} minute(s) ago"
        else:
            return "just now"


class NotificationMarkReadSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    mark_all = serializers.BooleanField(default=False)