import logging
from rest_framework import serializers
from django.utils import timezone

from users.models import LoginCheckpoint, User
from users.serializers.user import UserMinimalSerializer
from users.services.login_checkpoint import LoginCheckpointService

logger = logging.getLogger(__name__)


# ------------------ Minimal Serializer (for lists) ------------------
class LoginCheckpointMinimalSerializer(serializers.ModelSerializer):
    user_data = UserMinimalSerializer(source='user', read_only=True)
    status_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LoginCheckpoint
        fields = [
            'id',
            'user_data',
            'token',
            'created_at',
            'expires_at',
            'is_used',
            'status_display',
        ]
        read_only_fields = fields

    def get_status_display(self, obj) -> str:
        if obj.is_used:
            return "Used"
        if timezone.now() > obj.expires_at:
            return "Expired"
        return "Active"


# ------------------ Create Serializer (uses service) ------------------


class LoginCheckpointCreateSerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=True
    )

    def create(self, validated_data):
        user: User = validated_data['user']

        try:
            checkpoint = LoginCheckpointService.create_checkpoint(
                user=user,
                email=user.email
                # expiration handled internally by service
            )
            return checkpoint
        except Exception as e:
            logger.error(f"Login checkpoint creation failed via service: {e}")
            raise serializers.ValidationError(str(e))


# ------------------ Display Serializer (full detail) ------------------
class LoginCheckpointDisplaySerializer(serializers.ModelSerializer):
    user_data = UserMinimalSerializer(source='user', read_only=True)
    status_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LoginCheckpoint
        fields = [
            'id',
            'user',
            'user_data',
            'token',
            'created_at',
            'expires_at',
            'is_used',
            'status_display',
        ]
        read_only_fields = [
            'id', 'token', 'created_at', 'expires_at', 'is_used'
        ]

    def get_status_display(self, obj) -> str:
        if obj.is_used:
            return "Used"
        if timezone.now() > obj.expires_at:
            return "Expired"
        return "Active"


# ------------------ Response serializers for drf-spectacular ------------------
class LoginCheckpointListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = LoginCheckpointMinimalSerializer(many=True)


class LoginCheckpointDetailResponseSerializer(serializers.Serializer):
    data = LoginCheckpointDisplaySerializer()


class LoginCheckpointCreateResponseSerializer(serializers.Serializer):
    message = serializers.CharField(default="Login checkpoint created successfully")
    data = LoginCheckpointDisplaySerializer()


class LoginCheckpointUpdateResponseSerializer(serializers.Serializer):
    message = serializers.CharField(default="Login checkpoint updated successfully")
    data = LoginCheckpointDisplaySerializer()