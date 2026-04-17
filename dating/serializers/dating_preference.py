from rest_framework import serializers
from dating.models.dating_preference import DatingPreference
from users.models import User
from users.serializers.user.minimal import UserMinimalSerializer
from ..services.dating_preference import DatingPreferenceService


class DatingPreferenceMinimalSerializer(serializers.ModelSerializer):
    """Lightweight view for dating preferences."""

    class Meta:
        model = DatingPreference
        fields = [
            "preferred_age_min",
            "preferred_age_max",
            "preferred_gender",
            "max_distance_km",
        ]
        read_only_fields = fields


class DatingPreferenceCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating or updating dating preferences."""

    class Meta:
        model = DatingPreference
        fields = [
            "preferred_age_min",
            "preferred_age_max",
            "preferred_gender",
            "max_distance_km",
            "personality_match",
            "love_language_match",
            "relationship_goal_match",
        ]

    def create(self, validated_data):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        user = request.user
        # Delegate to service
        return DatingPreferenceService.update_preferences(user=user, update_data=validated_data)

    def update(self, instance, validated_data):
        request = self.context.get("request")
        user = request.user
        # Delegate to service
        return DatingPreferenceService.update_preferences(user=user, update_data=validated_data)


class DatingPreferenceDetailSerializer(serializers.ModelSerializer):
    """Detailed view for dating preferences."""

    user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = DatingPreference
        fields = [
            "id",
            "user",
            "preferred_age_min",
            "preferred_age_max",
            "preferred_gender",
            "max_distance_km",
            "personality_match",
            "love_language_match",
            "relationship_goal_match",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        

class DatingPreferenceCompatibilitySerializer(serializers.Serializer):
    """Serializer for checking compatibility between two users."""

    user2 = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
    )

    def validate_user2(self, value):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError("Request context not found")

        if request.user.id == value.id:
            raise serializers.ValidationError("Cannot check compatibility with yourself.")

        return value

    def create(self, validated_data):
        request = self.context.get("request")
        user1 = request.user
        user2 = validated_data["user2"]

        compatible = DatingPreferenceService.check_compatibility(user1=user1, user2=user2)
        return {
            "user1_id": user1.id,
            "user2_id": user2.id,
            "compatible": compatible,
        }