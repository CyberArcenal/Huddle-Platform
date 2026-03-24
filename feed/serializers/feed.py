# feed/serializers/feed.py

from typing import Any, Dict
from rest_framework import serializers
from events.serializers.event import EventListSerializer
from feed.models import Post, Reel, Share
from feed.serializers.post import PostFeedSerializer
from feed.serializers.reel import ReelDisplaySerializer, ReelMinimalSerializer
from feed.serializers.share import ShareFeedSerializer
from groups.serializers.group import GroupMinimalSerializer
from stories.serializers.base import StoryFeedSerializer, StorySerializer
from users.serializers.user import UserMinimalSerializer
from users.serializers.user_image import UserImageDisplaySerializer

FEED_DATA_TYPES = [
            "posts",
            "reels",
            "stories",
            "suggested_users",
            "match_users",
            "recommended_groups",
            "shares",
            "events",
            "post",
            "share",
            "reel",
            "story",
            "user_image",
            "ad",
            "ads",
            "other",
        ]

class StoryItemSerializer(serializers.Serializer):
    user = UserMinimalSerializer()
    stories = StoryFeedSerializer(many=True)
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



# Mapping from row_type to the serializer class for items
ROW_TYPE_SERIALIZER = {
    "posts": PostFeedSerializer,
    "reels": ReelMinimalSerializer,
    "stories": StoryItemSerializer,
    "suggested_users": SuggestedUserItemSerializer,
    "match_users": MatchUserItemSerializer,
    "recommended_groups": RecommendedGroupItemSerializer,
    "shares": ShareFeedSerializer,
    "events": EventListSerializer,
}

SINGLE_ITEM_SERIALIZER = {
    "post": PostFeedSerializer,
    "share": ShareFeedSerializer,
    "reel": ReelDisplaySerializer,
    "story": StorySerializer,
    "user_image": UserImageDisplaySerializer,
}


class UnifiedContentItemSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=FEED_DATA_TYPES)
    title = serializers.CharField(required=False, allow_blank=True)
    items = serializers.SerializerMethodField()
    item = serializers.SerializerMethodField()

    def get_items(self, obj) -> list[Dict[str, Any]]:
        # Rows have 'row_type' and 'items'
        if 'row_type' in obj and 'items' in obj:
            row_type = obj['row_type']
            items = obj['items']
            serializer_class = ROW_TYPE_SERIALIZER.get(row_type)
            if serializer_class:
                return serializer_class(items, many=True, context=self.context).data
        return []

    def get_item(self, obj) -> Dict[str, Any]:
        # Single items have 'type' and 'data'
        if 'type' in obj and 'item' in obj:
            content_type = obj['type']
            data_obj = obj['item']
            serializer_class = SINGLE_ITEM_SERIALIZER.get(content_type)
            if serializer_class:
                return serializer_class(data_obj, context=self.context).data
        return None

    def to_representation(self, instance):
        # Determine type and title based on input structure
        if 'row_type' in instance and 'items' in instance:
            type_val = instance.get('row_type')
            title = instance.get('title', '')
        elif 'type' in instance and 'item' in instance:
            type_val = instance.get('type')
            title = ''   # no title for single items
        else:
            type_val = 'other'
            title = ''

        # Use the methods to get the actual data
        items = self.get_items(instance)
        item = self.get_item(instance)

        return {
            'type': type_val,
            'title': title,
            'items': items,
            'item': item,
        }