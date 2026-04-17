from rest_framework import serializers
from users.models import User
from dating.models import Match
from dating.services.match import MatchService
from users.serializers.user.minimal import UserMinimalSerializer

class MatchMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for matches."""

    user1 = UserMinimalSerializer(read_only=True)
    user2 = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Match
        fields = ["id", "user1", "user2", "created_at", "is_active"]
        read_only_fields = fields


class MatchUnmatchSerializer(serializers.Serializer):
    """Serializer for unmatching (deactivating a match)."""

    match_id = serializers.IntegerField(write_only=True)

    def validate_match_id(self, value):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError("Request context not found")

        try:
            match = Match.objects.get(pk=value)
        except Match.DoesNotExist:
            raise serializers.ValidationError("Match record does not exist.")

        # Ensure the requesting user is part of the match
        if request.user not in [match.user1, match.user2]:
            raise serializers.ValidationError("You are not part of this match.")

        return value

    def create(self, validated_data):
        request = self.context.get("request")
        match_id = validated_data["match_id"]

        match = Match.objects.get(pk=match_id)
        # Delegate to service
        MatchService.deactivate_match(match)
        return {"success": True, "unmatched_id": match_id}

class MatchCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a match between two users."""

    user2 = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
    )

    class Meta:
        model = Match
        fields = ["user2"]

    def create(self, validated_data):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        user1 = request.user
        user2 = validated_data["user2"]

        # Delegate to service
        return MatchService.create_match(user1=user1, user2=user2)


class MatchDetailSerializer(serializers.ModelSerializer):
    """Detailed view for a match record."""

    user1 = UserMinimalSerializer(read_only=True)
    user2 = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Match
        fields = ["id", "user1", "user2", "created_at", "is_active"]
        read_only_fields = ["id", "created_at"]