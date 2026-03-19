from rest_framework import serializers




# Nested serializers para sa bawat method field
class FollowerSerializer(serializers.Serializer):
    follower_id = serializers.IntegerField()
    follower__username = serializers.CharField()
    created_at = serializers.DateTimeField()

class FollowingSerializer(serializers.Serializer):
    following_id = serializers.IntegerField()
    following__username = serializers.CharField()
    created_at = serializers.DateTimeField()

class ActivitySerializer(serializers.Serializer):
    action = serializers.CharField()
    description = serializers.CharField()
    timestamp = serializers.DateTimeField()
    ip_address = serializers.CharField()
    location = serializers.CharField()
    metadata = serializers.JSONField()

class SecurityLogSerializer(serializers.Serializer):
    event_type = serializers.CharField()
    created_at = serializers.DateTimeField()
    ip_address = serializers.CharField()
    user_agent = serializers.CharField()
    details = serializers.CharField()

class LoginSessionSerializer(serializers.Serializer):
    device_name = serializers.CharField()
    ip_address = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_used = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    is_active = serializers.BooleanField()