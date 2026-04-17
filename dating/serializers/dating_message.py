from rest_framework import serializers
from dating.models.dating_message import DatingMessage
from users.models import User
from users.serializers.user.minimal import UserMinimalSerializer
from ..services.dating_message import DatingMessageService


class DatingMessageMinimalSerializer(serializers.ModelSerializer):
    """Lightweight view for messages."""

    sender = UserMinimalSerializer(read_only=True)
    receiver = UserMinimalSerializer(read_only=True)

    class Meta:
        model = DatingMessage
        fields = ["id", "sender", "receiver", "content", "created_at", "is_read"]
        read_only_fields = fields


class DatingMessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for sending a new message."""

    receiver = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
    )

    class Meta:
        model = DatingMessage
        fields = ["receiver", "content"]

    def create(self, validated_data):
        from users.services.block import BlockedUserService
        blocked_ids = BlockedUserService.get_blocked_ids(request.user)
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        sender = request.user
        receiver = validated_data["receiver"]
        content = validated_data["content"]
        if receiver.id in blocked_ids:
            raise ValueError("Invalid User")
        # Delegate to service
        return DatingMessageService.send_message(sender=sender, receiver=receiver, content=content)


class DatingMessageDetailSerializer(serializers.ModelSerializer):
    """Detailed view for a message record."""

    sender = UserMinimalSerializer(read_only=True)
    receiver = UserMinimalSerializer(read_only=True)

    class Meta:
        model = DatingMessage
        fields = ["id", "sender", "receiver", "content", "created_at", "is_read"]
        read_only_fields = ["id", "created_at"]