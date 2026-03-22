from rest_framework import serializers

from feed.models.post_media import PostMedia


class PostMediaMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for post media."""
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = PostMedia
        fields = ['id', 'file_url', 'order']
        read_only_fields = fields

    def get_file_url(self, obj) -> str:
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None


class PostMediaCreateSerializer(serializers.ModelSerializer):
    """Used when creating media (usually part of post creation)."""
    class Meta:
        model = PostMedia
        fields = ['file', 'order']


class PostMediaDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single media item."""
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = PostMedia
        fields = ['id', 'file', 'file_url', 'order', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_file_url(self, obj) -> str:
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None