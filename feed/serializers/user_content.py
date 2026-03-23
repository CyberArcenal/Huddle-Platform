from rest_framework import serializers
from feed.serializers.post import PostFeedSerializer
from feed.serializers.share import ShareFeedSerializer
from feed.serializers.reel import ReelDisplaySerializer
from stories.serializers.base import StorySerializer
from users.serializers.user_image import UserImageDisplaySerializer


class UnifiedContentItemSerializer(serializers.Serializer):
    type = serializers.CharField()
    data = serializers.SerializerMethodField()

    def get_data(self, obj) -> serializers.DictField:
        content_type = obj['type']
        data_obj = obj['data']
        if content_type == 'post':
            return PostFeedSerializer(data_obj, context=self.context).data
        elif content_type == 'share':
            return ShareFeedSerializer(data_obj, context=self.context).data
        elif content_type == 'reel':
            return ReelDisplaySerializer(data_obj, context=self.context).data
        elif content_type == 'story':
            return StorySerializer(data_obj, context=self.context).data
        elif content_type == 'user_image':
            return UserImageDisplaySerializer(data_obj, context=self.context).data
        return None