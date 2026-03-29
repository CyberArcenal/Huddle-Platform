from typing import Optional

from django.conf import settings
from rest_framework import serializers

from feed.models.media import MEDIA_VARIANT_TYPES, Media, MediaVariant

class MediaVariantSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    variant_type = serializers.ChoiceField(choices=MEDIA_VARIANT_TYPES)

    class Meta:
        model = MediaVariant
        fields = [
            'variant_type',
            'file_url',
            'width',
            'height',
            'duration',
            'codec',
            'size_bytes',
            'created_at',
        ]
        read_only_fields = fields

    def get_file_url(self, obj) -> Optional[str]:
        request = self.context.get('request')
        if obj.file:
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

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
    mimeTypes = serializers.CharField(
        required=False,
        help_text="MIME type of the uploaded media file",
    )
    """Used when creating media (usually part of post creation)."""
    class Meta:
        model = Media
        fields = ['file', 'order', 'mimeTypes']

class MediaUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Media
        fields = ['order', 'metadata']
        
class MediaDisplaySerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()

    class Meta:
        model = Media
        fields = ['id', 'file_url', 'order', 'created_at', 'metadata', 'variants']
        read_only_fields = ['id', 'created_at']

    def get_file_url(self, obj) -> Optional[str]:
        request = self.context.get('request')
        if obj.file:
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


    def get_variants(self, obj) -> MediaVariantSerializer(many=True): # type: ignore
        """
        Return serialized MediaVariant objects.
        Uses the related MediaVariant objects instead of the metadata field.
        """
        request = self.context.get('request')
        variants = getattr(obj, '_prefetched_objects_cache', {}).get('variants', obj.variants.all())
        serializer = MediaVariantSerializer(variants, many=True, context={'request': request})
        return serializer.data