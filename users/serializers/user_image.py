# users/serializers/user_image.py
import os

from rest_framework import serializers
from feed.models.post import POST_PRIVACY_TYPES
from users.models import UserImage
from feed.serializers.base import PostStatsSerializers, ReactionCountSerializer
from feed.services.reaction import ReactionService
from feed.services.comment import CommentService
from users.models.user import PROFILE_IMAGE_TYPE_CHOICES
from users.serializers.user import UserMinimalSerializer
from users.services.user_image import UserImageService

class NormalizedImageField(serializers.ImageField):
    
    """
    ImageField that ensures uploaded file has a sensible filename extension
    (detects format with Pillow and appends extension if missing) BEFORE
    running the normal ImageField validation.
    """

    FORMAT_EXT_MAP = {
        "JPEG": ".jpg",
        "JPG": ".jpg",
        "PNG": ".png",
        "GIF": ".gif",
        "WEBP": ".webp",
        "TIFF": ".tiff",
    }

    def _ensure_name_has_extension(self, uploaded_file):
        from PIL import Image
        # If name already has extension, nothing to do
        name = getattr(uploaded_file, "name", "") or ""
        base, ext = os.path.splitext(name)
        if ext:
            return

        # Try detect format from file bytes
        try:
            uploaded_file.seek(0)
            img = Image.open(uploaded_file)
            fmt = (img.format or "").upper()
            detected_ext = self.FORMAT_EXT_MAP.get(fmt)
            if detected_ext:
                uploaded_file.name = f"{base or 'upload'}{detected_ext}"
        except Exception:
            # fallback: give a safe default extension so validators won't fail
            uploaded_file.name = f"{base or 'upload'}.jpg"
        finally:
            uploaded_file.seek(0)

    def to_internal_value(self, data):
        # data is usually an InMemoryUploadedFile or TemporaryUploadedFile
        try:
            if hasattr(data, "name"):
                self._ensure_name_has_extension(data)
        except Exception:
            # don't break validation flow; let parent handle any remaining errors
            pass

        return super().to_internal_value(data)

class UserImageMinimalSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = UserImage
        fields = ['id', 'image_url', 'caption', 'image_type', 'is_active', 'created_at']

    def get_image_url(self, obj):
        if obj.image:
            return self.context['request'].build_absolute_uri(obj.image.url)
        return None


class UserImageCreateSerializer(serializers.ModelSerializer):
    image_type = serializers.ChoiceField(choices=PROFILE_IMAGE_TYPE_CHOICES)
    privacy = serializers.ChoiceField(choices=POST_PRIVACY_TYPES, default='followers')
    image = NormalizedImageField(required=True, allow_empty_file=False)   # use the same field for validation
    crop_x = serializers.IntegerField(required=False, min_value=0, default=0)
    crop_y = serializers.IntegerField(required=False, min_value=0, default=0)
    crop_width = serializers.IntegerField(required=False, min_value=50, allow_null=True)
    crop_height = serializers.IntegerField(required=False, min_value=50, allow_null=True)

    class Meta:
        model = UserImage
        fields = ['image', 'caption', 'image_type', 'privacy', 'crop_x', 'crop_y', 'crop_width', 'crop_height']

    def validate(self, attrs):
        # Additional validation for image dimensions etc.
        # You can copy the validation from ProfilePictureUploadSerializer.validate_image_file
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        image_type = validated_data.pop('image_type')
        image_file = validated_data.pop('image')
        caption = validated_data.pop('caption', '')
        privacy = validated_data.pop('privacy', 'followers')
        crop_x = validated_data.pop('crop_x', 0)
        crop_y = validated_data.pop('crop_y', 0)
        crop_width = validated_data.pop('crop_width', None)
        crop_height = validated_data.pop('crop_height', None)

        # Use the service with optional crop parameters
        return UserImageService.set_active_image(
            user=user,
            image_type=image_type,
            image_file=image_file,
            caption=caption,
            privacy=privacy,
            crop_x=crop_x,
            crop_y=crop_y,
            crop_width=crop_width,
            crop_height=crop_height,
        )


class UserImageDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a user image with interaction statistics."""
    image_url = serializers.SerializerMethodField()
    user = UserMinimalSerializer(read_only=True)
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = UserImage
        fields = [
            'id', 'user', 'image_url', 'caption', 'image_type', 'is_active',
            'created_at', 'statistics'
        ]

    def get_image_url(self, obj):
        if obj.image:
            return self.context['request'].build_absolute_uri(obj.image.url)
        return None

    def get_user(self, obj):
        from users.serializers.user import UserMinimalSerializer
        return UserMinimalSerializer(obj.user, context=self.context).data

    def get_statistics(self, obj) -> PostStatsSerializers:#dont remove it, its use to detailed openapi schema
        from feed.services.post import PostService
        return PostService.get_post_statistics(serializer=self, obj=obj)
        
        
        
        
        
        
        
        
# ==============================================================================================

class UserMediaItemSerializer(serializers.Serializer):
    type = serializers.CharField()
    url = serializers.URLField(allow_null=True)
    thumbnail = serializers.URLField(allow_null=True, required=False)
    created_at = serializers.DateTimeField()
    content_id = serializers.IntegerField()
    content_type = serializers.CharField()
    media_order = serializers.IntegerField(allow_null=True)