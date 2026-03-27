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
        """
        Return a dictionary mapping variant type to absolute file URL.
        Uses the related MediaVariant objects instead of the metadata field.
        """
        request = self.context.get('request')
        if not request:
            return {}

        # Access the prefetched variants (to avoid N+1)
        variants = getattr(obj, '_prefetched_objects_cache', {}).get('variants', obj.variants.all())
        result = {}
        for variant in variants:
            if variant.file:
                result[variant.variant_type] = request.build_absolute_uri(variant.file.url)
            else:
                result[variant.variant_type] = None
        return result