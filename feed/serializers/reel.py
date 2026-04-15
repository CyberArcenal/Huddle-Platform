from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from rest_framework import serializers
import os
import tempfile
from django.core.exceptions import ValidationError
from rest_framework import serializers
from feed.models import Reel
from feed.models.post import POST_PRIVACY_TYPES
from feed.models.reaction import ReactionType
from feed.serializers.base import PostStatsSerializers, ReactionCountSerializer
from feed.serializers.comment import CommentDisplaySerializer
from feed.serializers.media import MediaDisplaySerializer
from feed.services.comment import CommentService
from feed.services.reel import ReelService
from feed.services.reaction import ReactionService
from feed.utils.media import extract_thumbnail
import os
import tempfile
import subprocess
import json
from django.core.exceptions import ValidationError
from rest_framework import serializers

from feed.models import Reel
from feed.services.reel import ReelService
from groups.serializers.group import GroupMinimalSerializer
from users.serializers.user.minimal import UserMinimalSerializer

class ReelMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for reels (e.g., in a feed)."""

    user = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer()
    video_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Reel
        fields = [
            "id",
            "user",
            "group",
            "caption",
            "video_url",
            "thumbnail_url",
            "duration",
            "created_at",
        ]
        read_only_fields = fields

    def get_video_url(self, obj) -> Optional[str]:
        try:
            request = self.context.get("request")
            media = obj.media.all().first()
            if media and not obj.processing and request:   # add condition
                return request.build_absolute_uri(media.file.url)
            return ""
        except:
            return None

    def get_thumbnail_url(self, obj) -> str:
        request = self.context.get("request")
        if obj.thumbnail and request:
            return request.build_absolute_uri(obj.thumbnail.url)
        return ""


class ReelCreateSerializer(serializers.ModelSerializer):
    client_id = serializers.CharField(required=False, allow_null=True, help_text="Unique ID to prevent duplicates")
    thumbnail = serializers.FileField(allow_null=True, required=False)
    caption = serializers.CharField(help_text="Optional caption for the reel", allow_blank=True)
    media = serializers.FileField(required=True, help_text="Video file for the reel (max 100MB, max duration 60s)")
    audio = serializers.FileField(allow_null=True, required=False)
    duration = serializers.IntegerField(help_text="Duration of the video in seconds (auto-validated, not user input)")
    privacy = serializers.ChoiceField(choices=POST_PRIVACY_TYPES)

    class Meta:
        model = Reel
        fields = ["caption", "media", "thumbnail", "audio", "duration", "privacy", "client_id"]

    # --- Added size validation for thumbnail and audio ---
    def validate_thumbnail(self, value):
        if value:
            max_size = getattr(settings, "MAX_THUMBNAIL_SIZE", 5 * 1024 * 1024)  # 5 MB default
            if value.size > max_size:
                raise serializers.ValidationError(
                    f"Thumbnail size exceeds limit ({max_size // (1024 * 1024)} MB)."
                )
        return value

    def validate_audio(self, value):
        if value:
            max_size = getattr(settings, "MAX_AUDIO_SIZE", 20 * 1024 * 1024)  # 20 MB default
            if value.size > max_size:
                raise serializers.ValidationError(
                    f"Audio file size exceeds limit ({max_size // (1024 * 1024)} MB)."
                )
        return value

    def validate_video(self, value):
        max_size_mb = getattr(settings, "MAX_REEL_VIDEO_SIZE", 100 * 1024 * 1024)  # 100 MB default
        if value.size > max_size_mb:
            raise serializers.ValidationError(
                f"Video file too large (max {max_size_mb // (1024 * 1024)} MB)."
            )

        try:
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
                for chunk in value.chunks():
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name

            # Use ffprobe to get duration
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'json',
                tmp_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            
            thumbnail_file, thumbnail_path = extract_thumbnail(value)
            self.context['thumbnail_file'] = thumbnail_file
            self.context['thumbnail_path'] = thumbnail_path

            # Clean up
            os.unlink(tmp_path)
            value.seek(0)

            if duration > 60:
                raise serializers.ValidationError(
                    f"Video duration must be 60 seconds or less. Current: {duration:.2f}s"
                )

            self.context['video_duration'] = duration

        except subprocess.CalledProcessError as e:
            raise serializers.ValidationError(
                f"Failed to read media duration. Ensure ffprobe is installed. Error: {e.stderr}"
            )
        except FileNotFoundError:
            raise serializers.ValidationError(
                "ffprobe not found. Please install ffmpeg and add it to your PATH."
            )
        except Exception as e:
            raise serializers.ValidationError(f"Error processing media: {str(e)}")

        return value

    def create(self, validated_data):
        validated_data['duration'] = self.context.get('video_duration')
        thumbnail_file = self.context.get('thumbnail_file')
        # Clean up temp file later if needed

        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError({"request": "Request context not found"})

        user = request.user
        try:
            return ReelService.create_reel(
                user=user,
                video=validated_data.get("media"),
                caption=validated_data.get("caption", ""),
                thumbnail=validated_data.get("thumbnail") or thumbnail_file,  # use generated if not provided
                audio=validated_data.get("audio"),
                duration=validated_data.get("duration"),
                client_id=validated_data.get("client_id"),
                privacy=validated_data.get("privacy", "public"),
            )
        except ValidationError as e:
            raise serializers.ValidationError(str(e))
        finally:
            # Clean up the temporary thumbnail file
            if 'thumbnail_path' in self.context:
                try:
                    os.unlink(self.context['thumbnail_path'])
                except OSError:
                    pass


# class ReelUpdateSerializer(serializers.ModelSerializer):
#     """Serializer for updating an existing reel (partial updates allowed)."""

#     class Meta:
#         model = Reel
#         fields = ["caption", "thumbnail", "audio", "duration", "privacy"]
#         extra_kwargs = {
#             "caption": {"required": False},
#             "thumbnail": {"required": False},
#             "audio": {"required": False},
#             "duration": {"required": False},
#             "privacy": {"required": False},
#         }

#     def update(self, instance, validated_data):
#         try:
#             return ReelService.update_reel(instance, validated_data)
#         except ValidationError as e:
#             raise serializers.ValidationError(str(e))


class ReelDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single reel, including engagement metrics and comments."""

    user = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer()
    video_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    media = MediaDisplaySerializer(many=True, read_only=True)
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Reel
        fields = [
            "id",
            "user",
            "group",
            "caption",
            "media",
            "video_url",
            "thumbnail_url",
            "audio_url",
            "duration",
            "privacy",
            "is_deleted",
            "is_archived",
            "created_at",
            "updated_at",
            "statistics",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "is_deleted"]

    def get_video_url(self, obj) -> Optional[str]:
        try:
            request = self.context.get("request")
            media = obj.media.all().first()
            if media and not obj.processing and request:   # add condition
                return request.build_absolute_uri(media.file.url)
            return ""
        except:
            return None

    def get_thumbnail_url(self, obj:Reel) -> Optional[str]:
        request = self.context.get("request")
        if obj.thumbnail_variant and obj.thumbnail_variant.file and request:
            return request.build_absolute_uri(obj.thumbnail_variant.file.url)
        return None

    def get_audio_url(self, obj) -> str:
        request = self.context.get("request")
        if obj.audio and request:
            return request.build_absolute_uri(obj.audio.url)
        return ""
    
    def get_statistics(self, obj) -> PostStatsSerializers:
        from feed.services.post import PostService
        return PostService.get_post_statistics(serializer=self, obj=obj)
    
    


class ReelUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating an existing reel.
    Supports partial updates. Only owner can update.
    Allowed fields: caption, privacy, is_archived, is_deleted, thumbnail, audio.
    """
    class Meta:
        model = Reel
        fields = [
            "caption",
            "privacy",
            "is_archived",
            "is_deleted",
            "thumbnail",
            "audio",
        ]
        extra_kwargs = {
            "caption": {"required": False, "allow_blank": True},
            "privacy": {"required": False},
            "is_archived": {"required": False},
            "is_deleted": {"required": False},
            "thumbnail": {"required": False},
            "audio": {"required": False},
        }

    def validate_privacy(self, value):
        if value not in dict(POST_PRIVACY_TYPES):
            raise serializers.ValidationError("Invalid privacy choice.")
        return value

    def update(self, instance, validated_data):
        # Direct update (file fields will be handled by Django's storage)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance