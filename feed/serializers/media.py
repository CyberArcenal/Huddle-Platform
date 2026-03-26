from django.conf import settings
from rest_framework import serializers

from feed.models.media import Media


class MediaMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for post media."""
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Media
        fields = ['id', 'file_url', 'order']
        read_only_fields = fields

    def get_file_url(self, obj) -> str:
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None


class MediaCreateSerializer(serializers.ModelSerializer):
    """Used when creating media (usually part of post creation)."""
    class Meta:
        model = Media
        fields = ['file', 'order']

class MediaUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Media
        fields = ['order', 'metadata']
        
class MediaDisplaySerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()

    class Meta:
        model = Media
        fields = ['id', 'file', 'file_url', 'order', 'created_at', 'metadata', 'variants']
        read_only_fields = ['id', 'created_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None

    def get_variants(self, obj):
        """Return a dictionary of variant URLs based on metadata."""
        request = self.context.get('request')
        variants = obj.metadata.get('variants', {})
        if not request:
            return variants  # fallback to raw data

        result = {}
        for name, info in variants.items():
            file_path = info.get('file')
            if file_path:
                # Assuming file_path is relative to MEDIA_URL
                result[name] = request.build_absolute_uri(settings.MEDIA_URL + file_path)
            else:
                result[name] = None
        return result