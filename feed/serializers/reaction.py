from typing import Dict, Any, Optional

from django.core.exceptions import ValidationError
from rest_framework import serializers

from feed.models import Reaction, Post, Comment
from feed.services.reaction import ReactionService
from users.serializers.user import UserMinimalSerializer
# Add to feed/serializers/reaction.py

class LikeDisplaySerializer(serializers.ModelSerializer):
    """Serializer for like objects (based on Reaction model, filtered to 'like')."""
    user = UserMinimalSerializer(read_only=True)
    content_object = serializers.SerializerMethodField()

    class Meta:
        model = Reaction
        fields = ['id', 'user', 'content_type', 'object_id', 'content_object', 'created_at']
        read_only_fields = fields

    def get_content_object(self, obj) -> Optional[Dict[str, Any]]:
        # Same implementation as in ReactionDisplaySerializer
        if obj.content_type == 'post':
            try:
                post = Post.objects.get(id=obj.object_id)
                return {
                    'type': 'post',
                    'id': post.id,
                    'content_preview': post.content[:100] if post.content else None,
                }
            except Post.DoesNotExist:
                return None
        elif obj.content_type == 'comment':
            try:
                comment = Comment.objects.get(id=obj.object_id)
                return {
                    'type': 'comment',
                    'id': comment.id,
                    'content_preview': comment.content[:100] if comment.content else None,
                }
            except Comment.DoesNotExist:
                return None
        return None


class LikeCreateSerializer(serializers.Serializer):
    """Serializer for creating a like (reaction_type forced to 'like')."""
    content_type = serializers.ChoiceField(choices=ReactionService.SERVICE_CONTENT_TYPES)
    object_id = serializers.IntegerField()

    def validate(self, data):
        content_type = data['content_type']
        object_id = data['object_id']
        # Validate target object exists (same as in ReactionCreateSerializer)
        model_map = {
            'post': Post,
            'comment': Comment,
        }
        if content_type in model_map:
            model = model_map[content_type]
            if not model.objects.filter(id=object_id, is_deleted=False).exists():
                raise serializers.ValidationError(f"{content_type} not found or deleted.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        try:
            created, reaction = ReactionService.add_like(
                user=request.user,
                content_type=validated_data['content_type'],
                object_id=validated_data['object_id']
            )
            if not created:
                raise serializers.ValidationError("Already liked.")
            return reaction
        except ValidationError as e:
            raise serializers.ValidationError(str(e))



class ReactionMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for reactions."""
    user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Reaction
        fields = ['id', 'user', 'reaction_type', 'created_at']
        read_only_fields = fields


from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers
from feed.models import Reaction, Post, Comment   # still needed for existence checks

class ReactionCreateSerializer(serializers.Serializer):
    content_type = serializers.CharField()   # was ChoiceField
    object_id = serializers.IntegerField()
    reaction_type = serializers.ChoiceField(
        choices=ReactionService.SERVICE_REACTION_TYPES,  # keep if you have it
        required=False,
        allow_blank=True,
        help_text="Send empty string or null to remove reaction"
    )

    def validate_content_type(self, value):
        try:
            ContentType.objects.get(model=value)
        except ContentType.DoesNotExist:
            raise serializers.ValidationError(f"Invalid content type '{value}'.")
        return value

    def validate(self, data):
        content_type = data['content_type']
        object_id = data['object_id']
        # Optional: verify the target object exists (if you have a base model with is_deleted)
        model_map = {
            'post': Post,
            'comment': Comment,
            # add others as needed
        }
        if content_type in model_map:
            model = model_map[content_type]
            if not model.objects.filter(id=object_id, is_deleted=False).exists():
                raise serializers.ValidationError(f"{content_type} not found or deleted.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        # ReactionService.set_reaction now expects content_type as string (model name)
        reacted, reaction = ReactionService.set_reaction(
            user=request.user,
            content_type=validated_data['content_type'],
            object_id=validated_data['object_id'],
            reaction_type=validated_data.get('reaction_type') or None
        )
        return {
            'reacted': reacted,
            'reaction': reaction,
            'reaction_type': reaction.reaction_type if reaction else None,
            'counts': ReactionService.get_reaction_counts(
                validated_data['content_type'], validated_data['object_id']
            )
        }


class ReactionDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a reaction, including user and content preview."""
    user = UserMinimalSerializer(read_only=True)
    content_object = serializers.SerializerMethodField()

    class Meta:
        model = Reaction
        fields = ['id', 'user', 'content_type', 'object_id', 'reaction_type', 'content_object', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_content_object(self, obj) -> Optional[Dict[str, Any]]:
        if obj.content_type == 'post':
            try:
                post = Post.objects.get(id=obj.object_id)
                return {
                    'type': 'post',
                    'id': post.id,
                    'content_preview': post.content[:100] if post.content else None,
                }
            except Post.DoesNotExist:
                return None
        elif obj.content_type == 'comment':
            try:
                comment = Comment.objects.get(id=obj.object_id)
                return {
                    'type': 'comment',
                    'id': comment.id,
                    'content_preview': comment.content[:100] if comment.content else None,
                }
            except Comment.DoesNotExist:
                return None
        return None


# Keep backward-compatible like toggle serializer if needed
class LikeToggleSerializer(serializers.Serializer):
    """Legacy serializer for toggling a like (uses reaction service)."""
    content_type = serializers.ChoiceField(choices=ReactionService.SERVICE_CONTENT_TYPES)
    object_id = serializers.IntegerField()

    def create(self, validated_data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        try:
            liked, reaction = ReactionService.toggle_like(
                user=request.user,
                content_type=validated_data['content_type'],
                object_id=validated_data['object_id']
            )
            return {
                'liked': liked,
                'like': reaction,
                'count': ReactionService.get_like_count(
                    validated_data['content_type'], validated_data['object_id']
                ),
            }
        except ValidationError as e:
            raise serializers.ValidationError(str(e))