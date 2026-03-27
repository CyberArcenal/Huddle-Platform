from rest_framework import serializers
from django.utils import timezone
from typing import Dict, Any, Optional

from feed.serializers.base import PostStatsSerializers
from feed.services.view import ViewService
from stories.models import Story
from stories.services.story import StoryService
from users.models import User
from users.serializers.user.minimal import UserMinimalSerializer

class StoryStatsSerializer(serializers.Serializer):
    total_stories = serializers.IntegerField()
    active_stories = serializers.IntegerField()
    expired_stories = serializers.IntegerField()
    total_views = serializers.IntegerField()


class StorySerializer(serializers.ModelSerializer):
    """Main Story serializer with read-only view count"""

    user = UserMinimalSerializer(read_only=True)
    has_viewed = serializers.SerializerMethodField()
    remaining_time = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    media_url = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = [
            "id",
            "user",
            "story_type",
            "content",
            "media_url",
            "expires_at",
            "is_active",
            "created_at",
            "has_viewed",
            "remaining_time",
            "is_expired",
            "statistics",
        ]
        read_only_fields = ["id", "user", "expires_at", "created_at", "is_active"]

    def get_media_url(self, obj) -> Optional[str]:
        request = self.context.get("request", None)
        try:
            if request:
                return request.build_absolute_uri(obj.media_url.url)
            else:
                return obj.media_url.url
        except Exception as e:
            return None

    def get_has_viewed(self, obj) -> bool:
        """Check if requesting user has viewed this story"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ViewService.has_viewed(obj, request.user)
        return False

    def get_remaining_time(self, obj) -> Optional[str]:
        """Calculate remaining time until expiration"""
        if obj.is_active and obj.expires_at > timezone.now():
            delta = obj.expires_at - timezone.now()
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        return None

    def get_is_expired(self, obj) -> bool:
        """Check if story is expired"""
        return not obj.is_active or obj.expires_at <= timezone.now()

    def get_statistics(self, obj) -> PostStatsSerializers:
        from feed.services.post import PostService
        return PostService.get_post_statistics(serializer=self, obj=obj)


class StoryCreateSerializer(serializers.Serializer):
    """Serializer for creating new stories using StoryService"""

    story_type = serializers.ChoiceField(choices=Story.STORY_TYPES)
    content = serializers.CharField(required=False, allow_blank=True)
    media_file = serializers.FileField(
        required=False, allow_null=True
    )  # <-- dati media_url
    expires_in_hours = serializers.IntegerField(default=24, min_value=1, max_value=168)

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate story creation data"""
        story_type = data.get("story_type")
        content = data.get("content")
        media_file = data.get("media_file")

        # Validate based on story type
        if story_type == "text" and not content:
            raise serializers.ValidationError(
                {"content": "Text stories require content"}
            )
        elif story_type in ["image", "video"] and not media_file:
            raise serializers.ValidationError(
                {"media_file": f"{story_type.capitalize()} stories require media"}
            )

        return data

    def create(self, validated_data: Dict[str, Any]) -> Story:
        """Create story using StoryService"""
        request = self.context.get("request")
        user = request.user

        return StoryService.create_story(
            user=user,
            story_type=validated_data["story_type"],
            content=validated_data.get("content"),
            media_file=validated_data.get("media_file"),  # <-- updated
            expires_in_hours=validated_data.get("expires_in_hours", 24),
        )


class StoryUpdateSerializer(serializers.Serializer):
    """Serializer for updating stories using StoryService"""

    content = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def update(self, story: Story, validated_data: Dict[str, Any]) -> Story:
        """Update story using StoryService"""
        return StoryService.update_story(story, validated_data)


class StoryFeedSerializer(serializers.Serializer):
    user = UserMinimalSerializer()
    stories = serializers.SerializerMethodField()
    has_viewed_all = serializers.SerializerMethodField()
    type = serializers.CharField(read_only=True)
    stories_count = serializers.SerializerMethodField()

    def _as_mapping(self, obj: Any) -> dict:
        """
        Normalize obj to a mapping-like object.
        If obj is a dict-like, return as-is.
        If obj is a Story instance (or model), wrap it into a dict with 'stories' key.
        """
        if obj is None:
            return {}
        if isinstance(obj, dict):
            return obj
        # If obj is a Story instance: treat it as single-story feed
        # If obj is a QuerySet or list of Story instances, caller should pass a dict,
        # but we still handle a single Story gracefully.
        if hasattr(obj, "_meta") and hasattr(obj, "id"):
            return {"user": getattr(obj, "user", None), "stories": [obj], "has_viewed_all": False, "type": "own"}
        # Fallback: try to coerce to dict
        try:
            return dict(obj)
        except Exception:
            return {}

    def get_stories_count(self, obj) -> int:
        data = self._as_mapping(obj)
        stories = data.get("stories", [])
        try:
            return len(stories)
        except Exception:
            return 0

    def get_has_viewed_all(self, obj) -> bool:
        data = self._as_mapping(obj)
        return bool(data.get("has_viewed_all", False))

    def get_stories(self, obj) -> StorySerializer(many=True): # type: ignore
        data = self._as_mapping(obj)
        stories = data.get("stories", []) or []

        if not stories:
            return []

        first = stories[0]
        # If first element is a dict, assume raw dicts already serialized
        if isinstance(first, dict):
            # Return raw dicts (or validate if you prefer)
            return stories
        # Otherwise assume model instances / QuerySet
        serializer = StorySerializer(stories, many=True, context=self.context)
        return serializer.data




class StoryStatsSerializer(serializers.Serializer):
    """Serializer for story statistics"""

    total_stories = serializers.IntegerField()
    active_stories = serializers.IntegerField()
    expired_stories = serializers.IntegerField()
    total_views = serializers.IntegerField()

    @staticmethod
    def get_stats(user: User) -> StoryStatsSerializer:
        """Get stats using StoryService"""
        return StoryService.get_story_stats(user)


class StoryHighlightSerializer(serializers.Serializer):
    """Serializer for story highlights"""

    story = StorySerializer()
    view_count = serializers.IntegerField()
    engagement_rate = serializers.FloatField()


class StoryRecommendationSerializer(serializers.Serializer):
    """Serializer for story recommendations"""

    user = UserMinimalSerializer()
    latest_story = StorySerializer()
    reason = serializers.CharField()


# Helper serializers for responses
class StoryViewCountSerializer(serializers.Serializer):
    """Serializer for view count response"""

    story_id = serializers.IntegerField()
    view_count = serializers.IntegerField()
    unique_viewers = serializers.IntegerField()


class StoryCleanupResponseSerializer(serializers.Serializer):
    """Serializer for cleanup operation response"""

    total = serializers.IntegerField()
    deactivated = serializers.IntegerField()
    deleted = serializers.IntegerField()


class StoryRecentViewerSerializer(serializers.Serializer):
    """Serializer for recent viewers"""

    user = UserMinimalSerializer()
    viewed_at = serializers.DateTimeField()
    time_ago = serializers.DurationField()
