from rest_framework import serializers
from users.models import User
from users.models.mute import MutedUser
from users.serializers.user.minimal import UserMinimalSerializer
from users.services.mute import MutedUserService


class MutedUserMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for muted users."""

    muted = UserMinimalSerializer(read_only=True)

    class Meta:
        model = MutedUser
        fields = ["id", "muted", "created_at"]
        read_only_fields = fields


class MutedUserCreateSerializer(serializers.ModelSerializer):
    """Serializer for muting a user."""

    muted_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = MutedUser
        fields = ["muted_id"]

    def create(self, validated_data):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        user = request.user
        muted_id = validated_data["muted_id"]

        try:
            muted_user = User.objects.get(pk=muted_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"muted_id": "Target user does not exist."})

        # Delegate to the service for business logic
        return MutedUserService.mute_user(user=user, muted=muted_user)



class UnMuteUserCreateSerializer(serializers.ModelSerializer):
    """Serializer for muting a user."""

    muted = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
    )

    class Meta:
        model = MutedUser
        fields = ["muted"]

    def create(self, validated_data):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        user = request.user
        muted_user = validated_data["muted"]

        # Delegate to service
        return MutedUserService.unmute_user(user=user, muted=muted_user)


class MutedUserDetailSerializer(serializers.ModelSerializer):
    """Detailed view for a muted user record."""

    user = UserMinimalSerializer(read_only=True)
    muted = UserMinimalSerializer(read_only=True)

    class Meta:
        model = MutedUser
        fields = ["id", "user", "muted", "created_at"]
        read_only_fields = ["id", "created_at"]