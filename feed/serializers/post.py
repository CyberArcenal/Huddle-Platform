from django.core.exceptions import ValidationError
from typing import Dict, Any, Optional
from rest_framework import serializers
from feed.models.base import Comment, Like, Post

from feed.services.comment import CommentService
from feed.services.like import LikeService
from feed.services.post import PostService
from users.models.base import User
from users.serializers.user import UserProfileSerializer


class PostSerializer(serializers.ModelSerializer):
    """Serializer for Post model"""

    user = UserProfileSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    comments = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    has_liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "user",
            "user_id",
            "content",
            "post_type",
            "media_url",
            "is_public",
            "is_deleted",
            "created_at",
            "updated_at",
            "comments",
            "comment_count",
            "like_count",
            "has_liked",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "is_deleted"]

    def get_comments(self, obj: Post) -> list:
        from feed.serializers.comment import CommentSerializer

        """Get top-level comments for this post"""
        comments = CommentService.get_post_comments(
            post=obj, include_replies=False, limit=10
        )
        return CommentSerializer(comments, many=True, context=self.context).data

    def get_comment_count(self, obj: Post) -> int:
        """Get total comment count for this post"""
        return CommentService.get_post_comment_count(obj)

    def get_like_count(self, obj: Post) -> int:
        """Get like count for this post"""
        return LikeService.get_like_count("post", obj.id)

    def get_has_liked(self, obj: Post) -> bool:
        """Check if current user has liked this post"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return LikeService.has_liked(
                user=request.user, content_type="post", object_id=obj.id
            )
        return False

    def validate_post_type(self, value: str) -> str:
        """Validate post_type field"""
        valid_types = [choice[0] for choice in Post.POST_TYPES]
        if value not in valid_types:
            raise serializers.ValidationError(f"post_type must be one of {valid_types}")
        return value

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate post data"""
        # Validate media_url based on post_type
        post_type = data.get("post_type", "text")
        media_url = data.get("media_url")

        if post_type in ["image", "video"] and not media_url:
            raise serializers.ValidationError(
                {"media_url": f"{post_type.capitalize()} posts require media_url"}
            )

        if post_type == "text" and not data.get("content", "").strip():
            raise serializers.ValidationError({"content": "Text posts require content"})

        # Validate user exists
        user_id = data.get("user_id")
        if user_id:
            try:
                User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise serializers.ValidationError(
                    {"user_id": "User with this ID does not exist"}
                )

        return data

    def create(self, validated_data: Dict[str, Any]) -> Post:
        """Create a post using PostService"""
        user = User.objects.get(id=validated_data["user_id"])

        try:
            post = PostService.create_post(
                user=user,
                content=validated_data["content"],
                post_type=validated_data.get("post_type", "text"),
                media_url=validated_data.get("media_url"),
                is_public=validated_data.get("is_public", True),
            )
            return post
        except ValidationError as e:
            raise serializers.ValidationError(str(e))

    def update(self, instance: Post, validated_data: Dict[str, Any]) -> Post:
        """Update a post using PostService"""
        try:
            updated_post = PostService.update_post(
                post=instance, update_data=validated_data
            )
            return updated_post
        except ValidationError as e:
            raise serializers.ValidationError(str(e))


class PostDetailSerializer(PostSerializer):
    """Extended serializer for detailed post view"""

    statistics = serializers.SerializerMethodField()

    class Meta(PostSerializer.Meta):
        fields = PostSerializer.Meta.fields + ["statistics"]

    def get_statistics(self, obj: Post) -> Dict[str, Any]:
        """Get detailed statistics for the post"""
        return PostService.get_post_statistics(obj)


class PostFeedSerializer(serializers.ModelSerializer):
    """Serializer for post feed (optimized for listing)"""

    user = UserProfileSerializer(read_only=True)
    preview = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "user",
            "content",
            "post_type",
            "media_url",
            "preview",
            "created_at",
            "statistics",
        ]

    def get_preview(self, obj: Post) -> str:
        """Get content preview (truncated)"""
        if obj.content:
            return obj.content[:150] + ("..." if len(obj.content) > 150 else "")
        return ""

    def get_statistics(self, obj: Post) -> Dict[str, Any]:
        """Get basic statistics for feed"""
        return {
            "comment_count": CommentService.get_post_comment_count(obj),
            "like_count": LikeService.get_like_count("post", obj.id),
            "is_public": obj.is_public,
        }


class PostStatisticsSerializer(serializers.Serializer):
    """Serializer for post statistics"""

    post_id = serializers.IntegerField()
    comment_count = serializers.IntegerField()
    like_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    is_public = serializers.BooleanField()
    post_type = serializers.CharField()


class UserPostStatisticsSerializer(serializers.Serializer):
    """Serializer for user post statistics"""

    total_posts = serializers.IntegerField()
    public_posts = serializers.IntegerField()
    private_posts = serializers.IntegerField()
    type_breakdown = serializers.ListField()
    first_post_date = serializers.DateTimeField(allow_null=True)


class SearchSerializer(serializers.Serializer):
    """Serializer for search operations"""

    query = serializers.CharField(required=True, max_length=255)
    post_type = serializers.CharField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
    offset = serializers.IntegerField(default=0, min_value=0)


class TrendingPostsSerializer(serializers.Serializer):
    """Serializer for trending posts"""

    post = PostSerializer()
    like_count = serializers.IntegerField()
    comment_count = serializers.IntegerField()
