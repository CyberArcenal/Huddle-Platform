# groups/serializers/suggestion.py
from rest_framework import serializers
from groups.serializers.group import GroupMinimalSerializer


class GroupSuggestionItemSerializer(serializers.Serializer):
    """Serializer for a single group suggestion item."""
    group = GroupMinimalSerializer()
    reason = serializers.CharField()
    score = serializers.FloatField()