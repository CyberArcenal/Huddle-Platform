from rest_framework import serializers
from users.models import User
from users.serializers.user.minimal import UserMinimalSerializer


class UserMatchScoreSerializer(serializers.Serializer):
    """Serializer for a user with match score."""
    user = UserMinimalSerializer(read_only=True)
    score = serializers.IntegerField()
    reasons = serializers.ListField(
        child=serializers.CharField(), required=False
    )



class UserMutualCountSerializer(serializers.Serializer):
    """Serializer for a user with mutual friend count."""
    user = UserMinimalSerializer(read_only=True)
    mutual_count = serializers.IntegerField()
    reason = serializers.CharField(required=False)



class FriendSuggestionsSerializer(serializers.Serializer):
    """Serializer for the combined friend suggestions response."""
    suggested_by_friends = UserMutualCountSerializer(many=True)
    best_matches = UserMatchScoreSerializer(many=True)