from rest_framework import serializers
from users.models.friendship import RELATIONSHIP_TAGS, Friendship
from users.models import User
from users.serializers.user.minimal import UserMinimalSerializer
from users.services.friendship import FriendshipService
from django.db.models import Q

class FriendshipMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for friendships."""

    friend = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Friendship
        fields = ["id", "friend", "tag", "status", "created_at"]
        read_only_fields = fields


class FriendshipCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating or updating a friendship request."""

    to_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
    )

    class Meta:
        model = Friendship
        fields = ["to_user", "tag", "status"]

    def create(self, validated_data):
        from users.services.block import BlockedUserService
            
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})
        blocked_ids = BlockedUserService.get_blocked_ids(request.user)
        from_user = request.user
        to_user = validated_data["to_user"]
        
        if to_user.id in blocked_ids:
            raise serializers.ValidationError({"blocked": "Cannot perform on blocked user"})

        # Delegate to service
        return FriendshipService.send_request(
            from_user=from_user,
            to_user=to_user,
            tag=validated_data.get("tag", "normal"),
        )

    def update(self, instance, validated_data):
        new_tag = validated_data.get("tag", instance.tag)
        new_status = validated_data.get("status", instance.status)

        if new_tag != instance.tag:
            FriendshipService.update_tag(instance, new_tag)

        if new_status != instance.status:
            if new_status == "accepted":
                FriendshipService.accept_request(instance)
            elif new_status == "declined":
                FriendshipService.decline_request(instance)

        return instance


class FriendshipDetailSerializer(serializers.ModelSerializer):
    """Detailed view for a friendship record."""

    user = UserMinimalSerializer(read_only=True)
    friend = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Friendship
        fields = [
            "id",
            "user",
            "friend",
            "status",
            "tag",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        
class TagUpdateSerializer(serializers.Serializer):
    tag = serializers.ChoiceField(choices=RELATIONSHIP_TAGS)
    
    def validate_tag(self, value):
        if value not in [choice[0] for choice in RELATIONSHIP_TAGS]:
            raise serializers.ValidationError("Invalid tag value.")
        return value
    
    def update(self, instance, validated_data):
        new_tag = validated_data.get("tag", instance.tag)
        if new_tag != instance.tag:
            FriendshipService.update_tag(instance, new_tag)
        return instance

class FriendRemoveSerializer(serializers.Serializer):
    friend = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
    )
    """Serializer for removing a friend (deleting a friendship)."""

    def delete(self, instance, validated_data):
        request = self.context.get("request", None)
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})
        
        instance = Friendship.objects.filter(
            Q(from_user=request.user, to_user=validated_data["friend"], status="accepted") & Q(from_user=validated_data["friend"], to_user=request.user, status="accepted")
        ).first()
        if not instance:
            raise serializers.ValidationError({"friend": "Friendship not found"})
        FriendshipService.remove_friendship(instance)
        return {"status": True, "message": "Friend removed successfully.", "data": None}