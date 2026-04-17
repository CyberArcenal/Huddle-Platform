from rest_framework import serializers
from users.models.blocked import BlockedUser
from users.models import User
from users.serializers.user.minimal import UserMinimalSerializer
from users.services.block import BlockedUserService

class BlockedUserMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for blocked users."""

    blocked = UserMinimalSerializer(read_only=True)

    class Meta:
        model = BlockedUser
        fields = ["id", "blocked", "created_at"]
        read_only_fields = fields


class BlockedUserCreateSerializer(serializers.ModelSerializer):
    """Serializer for blocking a user."""

    blocked = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
    )

    class Meta:
        model = BlockedUser
        fields = ["blocked"]

    def create(self, validated_data):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        user = request.user
        blocked_user = validated_data["blocked"]

        # Delegate to service
        return BlockedUserService.block_user(user=user, blocked=blocked_user)


class BlockedUserDetailSerializer(serializers.ModelSerializer):
    """Detailed view for a blocked user record."""

    user = UserMinimalSerializer(read_only=True)
    blocked = UserMinimalSerializer(read_only=True)

    class Meta:
        model = BlockedUser
        fields = ["id", "user", "blocked", "created_at"]
        read_only_fields = ["id", "created_at"]