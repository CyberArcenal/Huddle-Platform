from rest_framework import serializers
from live.models.live import LiveStream, LiveParticipant, LiveJoinRequest
from users.serializers.user.base import PostStatsSerializers
from users.serializers.user.minimal import UserMinimalSerializer


class LiveStreamSerializer(serializers.ModelSerializer):
    host = UserMinimalSerializer(read_only=True)
    participant_count = serializers.SerializerMethodField()
    viewer_count = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = LiveStream
        fields = [
            'id', 'host', 'title', 'description', 'status', 'started_at', 'ended_at',
            'thumbnail', 'allow_requests', 'max_participants', 'is_private',
            'participant_count', 'viewer_count', 'statistics', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'started_at', 'ended_at', 'created_at', 'stream_key']

    def get_participant_count(self, obj):
        return obj.participants.filter(left_at__isnull=True).count()

    def get_viewer_count(self, obj):
        return obj.participants.filter(role='viewer', left_at__isnull=True).count()
    
    def get_statistics(self, obj) -> PostStatsSerializers:
        from feed.services.post import PostService

        return PostService.get_post_statistics(serializer=self, obj=obj)


class LiveCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    allow_requests = serializers.BooleanField(default=True)
    max_participants = serializers.IntegerField(min_value=1, max_value=50, default=10)
    is_private = serializers.BooleanField(default=False)


class LiveJoinRequestSerializer(serializers.ModelSerializer):
    user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = LiveJoinRequest
        fields = ['id', 'user', 'status', 'requested_at', 'responded_at', 'message']
        read_only_fields = ['id', 'status', 'requested_at', 'responded_at']


class LiveParticipantSerializer(serializers.ModelSerializer):
    user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = LiveParticipant
        fields = ['id', 'user', 'role', 'joined_at', 'left_at']
        read_only_fields = ['id', 'joined_at', 'left_at']