from rest_framework import serializers
from django.utils import timezone
from typing import Dict, Any, List, Optional

from feed.models.reaction import ReactionType
from feed.serializers.base import ReactionCountSerializer
from feed.serializers.comment import CommentDisplaySerializer
from feed.services.comment import CommentService
from feed.services.reaction import ReactionService
from stories.models.base import Story, StoryView
from stories.services.story import StoryService
from stories.services.story_view import StoryViewService
from users.models.base import User
from users.serializers.user import UserMinimalSerializer
class StoryStatsSerializer(serializers.Serializer):
    total_stories = serializers.IntegerField()
    active_stories = serializers.IntegerField()
    expired_stories = serializers.IntegerField()
    total_views = serializers.IntegerField()


class StorySerializer(serializers.ModelSerializer):
    """Main Story serializer with read-only view count"""

    user = UserMinimalSerializer(read_only=True)
    view_count = serializers.SerializerMethodField()
    has_viewed = serializers.SerializerMethodField()
    remaining_time = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    media_url = serializers.SerializerMethodField()
    
    comments = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    
    like_count = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    reaction_counts = serializers.SerializerMethodField()
    user_reaction = serializers.SerializerMethodField()

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
            "view_count",
            "has_viewed",
            "remaining_time",
            "is_expired",
            
            "comments",
            "comment_count",
            
            "like_count",
            "liked",
            "reaction_counts",
            "user_reaction",
        ]
        read_only_fields = ["id", "user", "expires_at", "created_at", "is_active"]

    def get_media_url(self, obj) -> str:
        request = self.context.get("request", None)
        if request:
            return request.build_absolute_uri(obj.media_url.url)
        else:
            return obj.media_url.url

    def get_view_count(self, obj) -> int:
        """Get story view count using service"""
        return StoryViewService.get_story_view_count(obj)

    def get_has_viewed(self, obj) -> bool:
        """Check if requesting user has viewed this story"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return StoryViewService.has_viewed(obj, request.user)
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
    
    def get_reaction_counts(self, obj) -> ReactionCountSerializer:
        return ReactionService.get_reaction_counts(obj, obj.id)

    def get_user_reaction(self, obj) -> Optional[ReactionType]:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.get_user_reaction(request.user, obj, obj.id)
        return None

    def get_like_count(self, obj) -> int:
        return ReactionService.get_like_count(obj, obj.id)

    def get_liked(self, obj) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return ReactionService.has_liked(
                user=request.user, content_type=obj, object_id=obj.id
            )
        return False
    
    def get_comments(self, obj) -> CommentDisplaySerializer(many=True):  # type: ignore
        comments = CommentService.get_comments_for_object(
            content_object=obj, include_replies=False, limit=10
        )
        return CommentDisplaySerializer(comments, many=True, context=self.context).data

    def get_comment_count(self, obj) -> int:
        return CommentService.get_comment_count(obj)


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


class StoryViewSerializer(serializers.ModelSerializer):
    """Story View serializer"""

    user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = StoryView
        fields = ["id", "story", "user", "viewed_at"]
        read_only_fields = ["id", "user", "viewed_at"]


class StoryViewCreateSerializer(serializers.Serializer):
    """Serializer for recording story views using StoryViewService"""

    story_id = serializers.IntegerField()

    def validate_story_id(self, value: int) -> int:
        """Validate story exists and is viewable"""
        story = StoryService.get_story_by_id(value)
        if not story:
            raise serializers.ValidationError("Story not found")

        if not story.is_active:
            raise serializers.ValidationError("Story is not active")

        if story.expires_at <= timezone.now():
            raise serializers.ValidationError("Story has expired")

        return value

    def create(self, validated_data: Dict[str, Any]) -> StoryView:
        """Record story view using StoryViewService"""
        request = self.context.get("request")
        user = request.user
        story = StoryService.get_story_by_id(validated_data["story_id"])

        return StoryViewService.record_view(story, user)


class StoryFeedSerializer(serializers.Serializer):
    """Serializer for story feed using StoryFeedService"""

    user = UserMinimalSerializer()
    stories = serializers.SerializerMethodField()
    has_viewed_all = serializers.BooleanField()
    type = serializers.CharField()  # 'own', 'following', 'discovery'
    stories_count = serializers.SerializerMethodField()

    def get_stories_count(self, obj) -> int:
        """Get count of stories"""
        return len(obj.get("stories", []))

    def get_stories(self, obj) -> StorySerializer(many=True): # type: ignore
        """Pass context down to StorySerializer"""
        stories = obj.get("stories", [])
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
