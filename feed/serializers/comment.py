from django.core.exceptions import ValidationError
from typing import Dict, Any, Optional
from rest_framework import serializers
from feed.models.base import Comment, Like, Post
from feed.services.comment import CommentService
from feed.services.like import LikeService
from feed.services.post import PostService
from users.models.base import User
from users.serializers.user import UserProfileSerializer

class CommentCreateSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(write_only=True)
    post_id = serializers.IntegerField(write_only=True)
    parent_comment_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = Comment
        fields = ["user_id", "post_id", "parent_comment_id", "content"]
        
class CommentSerializer(serializers.ModelSerializer):
    """Serializer for Comment model"""

    user = UserProfileSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    post_id = serializers.IntegerField(write_only=True)
    parent_comment_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )
    replies = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    has_liked = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "post",
            "post_id",
            "user",
            "user_id",
            "parent_comment",
            "parent_comment_id",
            "content",
            "created_at",
            "replies",
            "like_count",
            "has_liked",
        ]
        read_only_fields = ["id", "created_at", "is_deleted"]
        extra_kwargs = {
            "post": {"read_only": True},
            "parent_comment": {"read_only": True},
        }

    def get_replies(self, obj: Comment) -> list:
        """Get serialized replies for this comment"""
        replies = CommentService.get_comment_replies(obj, limit=10)
        return CommentSerializer(replies, many=True, context=self.context).data

    def get_like_count(self, obj: Comment) -> int:
        """Get like count for this comment"""
        return LikeService.get_like_count("comment", obj.id)

    def get_has_liked(self, obj: Comment) -> bool:
        """Check if current user has liked this comment"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return LikeService.has_liked(
                user=request.user, content_type="comment", object_id=obj.id
            )
        return False

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate comment data"""
        post_id = data.get("post_id")
        parent_comment_id = data.get("parent_comment_id")
        user_id = data.get("user_id")

        # Validate post exists and not deleted
        try:
            post = Post.objects.get(id=post_id, is_deleted=False)
        except Post.DoesNotExist:
            raise serializers.ValidationError(
                {"post_id": "Post with this ID does not exist or is deleted"}
            )

        # Validate user exists
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"user_id": "User with this ID does not exist"}
            )

        # Validate parent comment if provided
        if parent_comment_id:
            try:
                parent_comment = Comment.objects.get(id=parent_comment_id)
                if parent_comment.post.id != post_id:
                    raise serializers.ValidationError(
                        {
                            "parent_comment_id": "Parent comment must belong to the same post"
                        }
                    )
            except Comment.DoesNotExist:
                raise serializers.ValidationError(
                    {"parent_comment_id": "Parent comment with this ID does not exist"}
                )

        return data

    def create(self, validated_data: Dict[str, Any]) -> Comment:
        """Create a comment using CommentService"""
        post = Post.objects.get(id=validated_data["post_id"])
        user = User.objects.get(id=validated_data["user_id"])
        parent_comment = None

        if validated_data.get("parent_comment_id"):
            parent_comment = Comment.objects.get(id=validated_data["parent_comment_id"])

        try:
            comment = CommentService.create_comment(
                post=post,
                user=user,
                content=validated_data["content"],
                parent_comment=parent_comment,
            )
            return comment
        except ValidationError as e:
            raise serializers.ValidationError(str(e))

    def update(self, instance: Comment, validated_data: Dict[str, Any]) -> Comment:
        """Update a comment using CommentService"""
        try:
            updated_comment = CommentService.update_comment(
                comment=instance,
                new_content=validated_data.get("content", instance.content),
            )
            return updated_comment
        except ValidationError as e:
            raise serializers.ValidationError(str(e))
