# portfolio/serializers/notifylog.py
from rest_framework import serializers

from notifications.models.notify_log import NotifyLog


class NotifyLogMinimalSerializer(serializers.ModelSerializer):
    """Lightweight log entry for listings"""

    class Meta:
        model = NotifyLog
        fields = ['id', 'recipient_email', 'subject', 'status', 'created_at']


class NotifyLogDisplaySerializer(serializers.ModelSerializer):
    """Full log details for inspection"""

    class Meta:
        model = NotifyLog
        fields = [
            'id', 'recipient_email', 'subject', 'payload', 'status',
            'error_message', 'channel', 'priority', 'message_id',
            'duration_ms', 'retry_count', 'resend_count', 'sent_at',
            'last_error_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class NotifyLogCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating log entries (usually via system)"""

    class Meta:
        model = NotifyLog
        fields = [
            'recipient_email', 'subject', 'payload', 'status',
            'error_message', 'channel', 'priority', 'message_id',
            'duration_ms', 'retry_count', 'resend_count', 'sent_at',
            'last_error_at'
        ]

    def create(self, validated_data):
        return NotifyLog.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def to_representation(self, instance):
        return NotifyLogDisplaySerializer(instance, context=self.context).data