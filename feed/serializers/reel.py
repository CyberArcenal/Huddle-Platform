from typing import Optional

from django.core.exceptions import ValidationError
from rest_framework import serializers
import os
import tempfile
from django.core.exceptions import ValidationError
from rest_framework import serializers
from feed.models import Reel
from feed.models.reaction import ReactionType
from feed.serializers.base import PostStatsSerializers, ReactionCountSerializer
from feed.serializers.comment import CommentDisplaySerializer
from feed.services.comment import CommentService
from feed.services.reel import ReelService
from feed.services.reaction import ReactionService
from feed.utils.media import extract_thumbnail
from users.serializers.user import UserMinimalSerializer, UserMinimalSerializer
import os
import tempfile
import subprocess
import json
from django.core.exceptions import ValidationError
from rest_framework import serializers

from feed.models import Reel
from feed.services.reel import ReelService

class ReelMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for reels (e.g., in a feed)."""

    user = UserMinimalSerializer(read_only=True)
    video_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Reel
        fields = [
            "id",
            "user",
            "caption",
            "video_url",
            "thumbnail_url",
            "duration",
            "created_at",
        ]
        read_only_fields = fields

    def get_video_url(self, obj) -> str:
        request = self.context.get("request")
        if obj.media and request:
            return request.build_absolute_uri(obj.media.url)
        return ""

    def get_thumbnail_url(self, obj) -> str:
        request = self.context.get("request")
        if obj.thumbnail and request:
            return request.build_absolute_uri(obj.thumbnail.url)
        return ""





class ReelCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reel
        fields = ["caption", "media", "thumbnail", "audio", "duration", "privacy"]

    def validate_video(self, value):
        # File size limit
        max_size_mb = 100
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"Video file too large (max {max_size_mb} MB)."
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
                video=validated_data.get("video"),
                caption=validated_data.get("caption", ""),
                thumbnail=validated_data.get("thumbnail") or thumbnail_file,  # use generated if not provided
                audio=validated_data.get("audio"),
                duration=validated_data.get("duration"),
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


class ReelUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating an existing reel (partial updates allowed)."""

    class Meta:
        model = Reel
        fields = ["caption", "thumbnail", "audio", "duration", "privacy"]
        extra_kwargs = {
            "caption": {"required": False},
            "thumbnail": {"required": False},
            "audio": {"required": False},
            "duration": {"required": False},
            "privacy": {"required": False},
        }

    def update(self, instance, validated_data):
        try:
            return ReelService.update_reel(instance, validated_data)
        except ValidationError as e:
            raise serializers.ValidationError(str(e))


class ReelDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single reel, including engagement metrics and comments."""

    user = UserMinimalSerializer(read_only=True)
    video_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    has_liked = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()  # first few comments
    reaction_counts = serializers.SerializerMethodField()
    user_reaction = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Reel
        fields = [
            "id",
            "user",
            "caption",
            "video_url",
            "thumbnail_url",
            "audio_url",
            "duration",
            "privacy",
            "created_at",
            "updated_at",
            "like_count",
            "comment_count",
            "has_liked",
            "comments",
            "reaction_counts",
            "user_reaction",
            "statistics",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "is_deleted"]

    def get_video_url(self, obj) -> str:
        request = self.context.get("request")
        if obj.media and request:
            return request.build_absolute_uri(obj.media.url)
        return ""

    def get_thumbnail_url(self, obj) -> str:
        request = self.context.get("request")
        if obj.thumbnail and request:
            return request.build_absolute_uri(obj.thumbnail.url)
        return ""

    def get_audio_url(self, obj) -> str:
        request = self.context.get("request")
        if obj.audio and request:
            return request.build_absolute_uri(obj.audio.url)
        return ""
    
    def get_reaction_counts(self, obj) -> ReactionCountSerializer:
        return ReactionService.get_reaction_counts(obj, obj.id)
    
    def get_user_reaction(self, obj) -> ReactionType:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.get_user_reaction(request.user, obj, obj.id)
        return None

    def get_like_count(self, obj) -> int:
        return ReactionService.get_like_count(obj, obj.id)

    def get_comment_count(self, obj) -> int:
        return CommentService.get_comment_count(obj)

    def get_has_liked(self, obj) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.has_liked(
                user=request.user, content_type=obj, object_id=obj.id
            )
        return False

    def get_comments(self, obj) -> CommentDisplaySerializer(many=True):  # type: ignore

        comments = CommentService.get_comments_for_object(
            obj, include_replies=False, limit=3
        )
        return CommentDisplaySerializer(
            comments, many=True, context=self.context
        ).data
    def get_statistics(self, obj) -> PostStatsSerializers:
        from feed.services.post import PostService
        return PostService.get_post_statistics(serializer=self, obj=obj)
