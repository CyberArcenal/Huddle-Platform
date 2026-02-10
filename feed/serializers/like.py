from django.core.exceptions import ValidationError
from typing import Dict, Any, Optional
from rest_framework import serializers
from feed.models.base import Comment, Like, Post
from feed.services.comment import CommentService
from feed.services.like import LikeService
from feed.services.post import PostService
from users.models.base import User
from users.serializers.user import UserProfileSerializer


class LikeSerializer(serializers.ModelSerializer):
    """Serializer for Like model"""

    user = UserProfileSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Like
        fields = ["id", "user", "user_id", "content_type", "object_id", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_content_type(self, value: str) -> str:
        """Validate content_type field"""
        if value not in LikeService.CONTENT_TYPES:
            raise serializers.ValidationError(
                f"content_type must be one of {LikeService.CONTENT_TYPES}"
            )
        return value

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the entire like data"""
        content_type = data.get("content_type")
        object_id = data.get("object_id")
        user_id = data.get("user_id")

        # Check if object exists based on content_type
        if content_type == "post":
            try:
                Post.objects.get(id=object_id, is_deleted=False)
            except Post.DoesNotExist:
                raise serializers.ValidationError(
                    {"object_id": "Post with this ID does not exist or is deleted"}
                )
        elif content_type == "comment":
            try:
                Comment.objects.get(id=object_id)
            except Comment.DoesNotExist:
                raise serializers.ValidationError(
                    {"object_id": "Comment with this ID does not exist"}
                )

        # Check if user exists
        try:
            User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"user_id": "User with this ID does not exist"}
            )

        return data

    def create(self, validated_data: Dict[str, Any]) -> Like:
        """Create a like using LikeService"""
        user = User.objects.get(id=validated_data["user_id"])

        try:
            created, like = LikeService.add_like(
                user=user,
                content_type=validated_data["content_type"],
                object_id=validated_data["object_id"],
            )

            if not created:
                raise serializers.ValidationError("Already liked")

            return like
        except ValidationError as e:
            raise serializers.ValidationError(str(e))

    def to_representation(self, instance: Like) -> Dict[str, Any]:
        """Custom representation for Like"""
        representation = super().to_representation(instance)

        # Add additional data based on content_type
        if instance.content_type == "post":
            try:
                post = Post.objects.get(id=instance.object_id)
                representation["content_object"] = {
                    "type": "post",
                    "id": post.id,
                    "content_preview": post.content[:100] if post.content else None,
                }
            except Post.DoesNotExist:
                representation["content_object"] = None
        elif instance.content_type == "comment":
            try:
                comment = Comment.objects.get(id=instance.object_id)
                representation["content_object"] = {
                    "type": "comment",
                    "id": comment.id,
                    "content_preview": (
                        comment.content[:100] if comment.content else None
                    ),
                }
            except Comment.DoesNotExist:
                representation["content_object"] = None

        return representation


class LikeToggleSerializer(serializers.Serializer):
    """Serializer for toggling likes"""

    content_type = serializers.CharField(required=True)
    object_id = serializers.IntegerField(required=True)

    def validate_content_type(self, value: str) -> str:
        """Validate content_type field"""
        if value not in LikeService.CONTENT_TYPES:
            raise serializers.ValidationError(
                f"content_type must be one of {LikeService.CONTENT_TYPES}"
            )
        return value

    def create(self, validated_data: Dict[str, Any]) -> Dict[str, Any]:
        """Toggle like using LikeService"""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        try:
            liked, like = LikeService.toggle_like(
                user=request.user,
                content_type=validated_data["content_type"],
                object_id=validated_data["object_id"],
            )

            return {
                "liked": liked,
                "like": like,
                "count": LikeService.get_like_count(
                    validated_data["content_type"], validated_data["object_id"]
                ),
            }
        except ValidationError as e:
            raise serializers.ValidationError(str(e))
