# feed/serializers/feed.py

from typing import Any, Dict
from rest_framework import serializers
from events.serializers.event import EventListSerializer
from feed.models import Post, Reel, Share
from feed.serializers.post import PostFeedSerializer
from feed.serializers.reel import ReelMinimalSerializer
from feed.serializers.share import ShareFeedSerializer
from groups.serializers.group import GroupMinimalSerializer
from stories.serializers.base import StorySerializer
from users.serializers.user import UserMinimalSerializer


class StoryItemSerializer(serializers.Serializer):
    user = UserMinimalSerializer()
    stories = StorySerializer(many=True)
    has_viewed_all = serializers.BooleanField()
    type = serializers.ChoiceField(choices=['following', 'own'])


class SuggestedUserItemSerializer(serializers.Serializer):
    user = UserMinimalSerializer()
    mutual_count = serializers.IntegerField()
    reason = serializers.CharField(allow_null=True, required=False)


class MatchUserItemSerializer(serializers.Serializer):
    user = UserMinimalSerializer()
    score = serializers.IntegerField()
    reasons = serializers.ListField(child=serializers.CharField(), required=False)


class RecommendedGroupItemSerializer(serializers.Serializer):
    group = GroupMinimalSerializer()
    score = serializers.FloatField()
    reason = serializers.CharField(allow_null=True, required=False)


class PostItemSerializer(PostFeedSerializer):
    """Wrapper for posts row items"""
    pass


class ReelItemSerializer(ReelMinimalSerializer):
    """Wrapper for reels row items"""
    pass


class ShareItemSerializer(ShareFeedSerializer):
    """Wrapper for shares row items"""
    pass


class EventItemSerializer(EventListSerializer):
    """Wrapper for events row items"""
    pass


# Mapping from row_type to the serializer class for items
ROW_TYPE_SERIALIZER = {
    "posts": PostItemSerializer,
    "reels": ReelItemSerializer,
    "stories": StoryItemSerializer,
    "suggested_users": SuggestedUserItemSerializer,
    "match_users": MatchUserItemSerializer,
    "recommended_groups": RecommendedGroupItemSerializer,
    "shares": ShareItemSerializer,
    "events": EventItemSerializer,
}


class FeedRowSerializer(serializers.Serializer):
    row_type = serializers.ChoiceField(
        choices=[
            "posts",
            "reels",
            "stories",
            "suggested_users",
            "match_users",
            "recommended_groups",
            "shares",
            "events",
            "other",
        ]
    )
    title = serializers.CharField()
    items = serializers.SerializerMethodField()

    def get_items(self, row) -> list[Dict[str, Any]]:
        row_type = row.get("row_type")
        items = row.get("items", [])
        serializer_class = ROW_TYPE_SERIALIZER.get(row_type)
        if serializer_class:
            return serializer_class(items, many=True, context=self.context).data
        # Fallback for unknown row types
        return items