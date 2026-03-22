from rest_framework import serializers


class UserMediaItemSerializer(serializers.Serializer):
    type = serializers.CharField()
    url = serializers.URLField(allow_null=True)
    thumbnail = serializers.URLField(allow_null=True, required=False)
    created_at = serializers.DateTimeField()
    content_id = serializers.IntegerField()
    content_type = serializers.CharField()
    media_order = serializers.IntegerField(allow_null=True)