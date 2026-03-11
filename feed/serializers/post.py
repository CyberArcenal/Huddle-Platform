import logging

from django.core.exceptions import ValidationError
from typing import Dict, Any, Optional, List
from rest_framework import serializers
from feed.models.base import Comment, Like, Post, PostMedia

from feed.serializers.comment import CommentSerializer
from feed.services.comment import CommentService
from feed.services.like import LikeService
from feed.services.post import PostService
from users.serializers.user import UserMinimalSerializer, UserProfileSerializer

logger = logging.getLogger(__name__)


class PostMediaSerializer(serializers.ModelSerializer):
    """Serializer for post media (images/videos)"""

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = PostMedia
        fields = ["id", "file", "file_url", "order", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_file_url(self, obj: PostMedia) -> Optional[str]:
        request = self.context.get('request', None)
        if request:
            return request.build_absolute_uri(obj.file.url)
        elif obj.file:
            return obj.file.url
        return None


# FOR SCHEMA ONLY
class PostCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new post. Accepts multiple media files."""

    content = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    media_files = serializers.ListField(
        child=serializers.FileField(), write_only=True, required=False, allow_empty=True
    )

    class Meta:
        model = Post
        fields = ["content", "post_type", "privacy", "media_files"]

    def validate(self, data):
        logger.debug(data)
        post_type = data.get("post_type", "text")
        media_files = data.get("media_files", [])

        if post_type in ["image", "video"] and not media_files:
            raise serializers.ValidationError(
                {
                    "media_files": f"{post_type.capitalize()} posts require at least one media file."
                }
            )
        if post_type == "text" and media_files:
            raise serializers.ValidationError(
                {"media_files": "Text posts cannot have media."}
            )
        if post_type == "text" and not data.get("content", "").strip():
            raise serializers.ValidationError(
                {"content": "Text posts require content."}
            )
        return data

    def create(self, validated_data: Dict[str, Any]) -> Post:
        """Create a post using PostService (should handle media via separate method)"""
        # Note: This method is rarely used because we use PostCreateSerializer for creation.
        # Kept for completeness, but media creation would need to be handled separately.
        request = self.context.get("request")
        if not request:
            raise Exception("Request not provided")
        # For simple text-only creation (no media), we can still use this.
        try:
            post = PostService.create_post(
                user=request.user,
                content=validated_data["content"],
                post_type=validated_data.get("post_type", "text"),
                media_files=validated_data.get("media_files", []),
                privacy=validated_data.get("privacy", "followers"),
            )
            return post
        except ValidationError as e:
            raise serializers.ValidationError(str(e))

    def update(self, instance: Post, validated_data: Dict[str, Any]) -> Post:
        """Update a post (media updates not handled here)"""
        try:
            updated_post = PostService.update_post(
                post=instance, update_data=validated_data
            )
            return updated_post
        except ValidationError as e:
            raise serializers.ValidationError(str(e))


# //FOR DETAILS
class PostSerializer(serializers.ModelSerializer):
    """Serializer for Post model with multiple media"""

    content = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    user = UserMinimalSerializer(read_only=True)
    media = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "user",
            "content",
            "post_type",
            "media",
            "privacy",
            "is_deleted",
            "created_at",
            "updated_at",
            "comments",
            "comment_count",
            "like_count",
            "liked",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "is_deleted"]
        
    def get_media(self, obj) -> Optional[List[Dict[str, Any]]]:
        return PostMediaSerializer(obj.media, many=True).data
    
    def get_comments(self, obj: Post) -> List[Dict[str, Any]]:
        """Get top-level comments for this post"""
        comments = CommentService.get_post_comments(
            post=obj, include_replies=False, limit=10
        )
        return CommentSerializer(comments, many=True, context=self.context).data

    def get_comment_count(self, obj: Post) -> int:
        return CommentService.get_post_comment_count(obj)

    def get_like_count(self, obj: Post) -> int:
        return LikeService.get_like_count("post", obj.id)

    def get_liked(self, obj: Post) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return LikeService.has_liked(
                user=request.user, content_type="post", object_id=obj.id
            )
        return False


class PostDetailSerializer(PostSerializer):
    """Extended serializer for detailed post view with statistics"""

    statistics = serializers.SerializerMethodField()

    class Meta(PostSerializer.Meta):
        fields = PostSerializer.Meta.fields + ["statistics"]

    def get_statistics(self, obj: Post) -> Dict[str, Any]:
        return PostService.get_post_statistics(obj)


class PostFeedSerializer(serializers.ModelSerializer):
    """Serializer for post feed (optimized for listing)"""

    user = UserProfileSerializer(read_only=True)
    preview = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()
    media = PostMediaSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = [
            "id",
            "user",
            "content",
            "post_type",
            "media",
            "preview",
            "created_at",
            "statistics",
        ]

    def get_preview(self, obj: Post) -> str:
        if obj.content:
            return obj.content[:150] + ("..." if len(obj.content) > 150 else "")
        return ""

    def get_statistics(self, obj: Post) -> Dict[str, Any]:
        """Get basic statistics for feed"""
        request = self.context.get("request")
        return {
            "comment_count": CommentService.get_post_comment_count(obj),
            "like_count": LikeService.get_like_count("post", obj.id),
            "privacy": obj.privacy,
            "comments": CommentSerializer(
                CommentService.get_post_comments(obj, limit=10), many=True
            ).data,
            "liked": (
                LikeService.has_liked(
                    user=request.user, content_type="post", object_id=obj.id
                )
                if request and request.user.is_authenticated
                else False
            ),
        }


# The following serializers remain unchanged as they don't directly involve media fields.
class PostStatisticsSerializer(serializers.Serializer):
    post_id = serializers.IntegerField()
    comment_count = serializers.IntegerField()
    like_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    privacy = serializers.BooleanField()
    post_type = serializers.CharField()


class UserPostStatisticsSerializer(serializers.Serializer):
    total_posts = serializers.IntegerField()
    public_posts = serializers.IntegerField()
    private_posts = serializers.IntegerField()
    type_breakdown = serializers.ListField()
    first_post_date = serializers.DateTimeField(allow_null=True)


class SearchSerializer(serializers.Serializer):
    query = serializers.CharField(required=True, max_length=255)
    post_type = serializers.CharField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
    offset = serializers.IntegerField(default=0, min_value=0)


class TrendingPostsSerializer(serializers.Serializer):
    post = PostSerializer()
    like_count = serializers.IntegerField()
    comment_count = serializers.IntegerField()
