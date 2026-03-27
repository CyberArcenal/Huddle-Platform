
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from feed.models import Reaction, Post, Comment
from feed.models.reaction import REACTION_TYPES
from feed.services.reaction import ReactionService
from users.serializers.user.minimal import UserMinimalSerializer

class ReactionDisplayContentData(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.IntegerField()
    content_preview = serializers.StringRelatedField()



class LikeCreateSerializer(serializers.Serializer):
    """Serializer for creating a like (reaction_type forced to 'like')."""
    content_type = serializers.CharField()
    object_id = serializers.IntegerField()

    def validate_content_type(self, value):
        """Ensure the content type (model name) exists."""
        try:
            ContentType.objects.get(model=value)
        except ContentType.DoesNotExist:
            raise serializers.ValidationError(f"Invalid content type '{value}'.")
        return value

    def validate(self, data):
        content_type = data['content_type']
        object_id = data['object_id']
        # Optional: verify the target object exists (if you have models with is_deleted)
        model_map = {
            'post': Post,
            'comment': Comment,
            # add other models as needed
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





class ReactionCreateSerializer(serializers.Serializer):
    """Serializer for creating/updating a reaction."""
    content_type = serializers.CharField()
    object_id = serializers.IntegerField()
    reaction_type = serializers.ChoiceField(
        choices=REACTION_TYPES,
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
        # Optional: verify the target object exists (if you have models with is_deleted)
        model_map = {
            'post': Post,
            'comment': Comment,
            # add other models as needed
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

        reacted, reaction = ReactionService.set_reaction(
            user=request.user,
            content_type=validated_data['content_type'],
            object_id=validated_data['object_id'],
            reaction_type=validated_data.get('reaction_type') or None
        )
        return {
            
            'object_id': validated_data['object_id'],
            'content_type': validated_data['content_type'],
            'reacted': reacted,
            'reaction_type': reaction.reaction_type if reaction else None,
            'reaction_count': ReactionService.get_total_reactions(validated_data['content_type'], validated_data['object_id']),
            'counts': ReactionService.get_reaction_counts(
                validated_data['content_type'], validated_data['object_id']
            )
        }


class ReactionMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for reactions."""
    user = UserMinimalSerializer(read_only=True)
    reaction_type = serializers.ChoiceField(
        choices=REACTION_TYPES
    )

    class Meta:
        model = Reaction
        fields = ['id', 'user', 'content_type', 'object_id', 'reaction_type', 'created_at']
        read_only_fields = fields

class ReactionDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a reaction, including user and content preview."""
    user = UserMinimalSerializer(read_only=True)
    content_object = serializers.SerializerMethodField()
    reaction_type = serializers.ChoiceField(
        choices=REACTION_TYPES
    )

    class Meta:
        model = Reaction
        fields = ['id', 'user', 'content_type', 'object_id', 'reaction_type', 'content_object', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_content_object(self, obj) -> ReactionDisplayContentData:
        """
        Returns a simplified representation of the reacted object.
        Uses the generic foreign key to fetch the related object.
        """
        if obj.content_object is None:
            return None

        model_name = obj.content_type.model
        result = {
            'type': model_name,
            'id': obj.object_id,
        }

        # Add a content preview for known types (optional)
        if model_name == 'post' and hasattr(obj.content_object, 'content'):
            result['content_preview'] = obj.content_object.content[:100]
        elif model_name == 'comment' and hasattr(obj.content_object, 'content'):
            result['content_preview'] = obj.content_object.content[:100]

        return result


class LikeToggleSerializer(serializers.Serializer):
    """Legacy serializer for toggling a like (uses reaction service)."""
    content_type = serializers.CharField()
    object_id = serializers.IntegerField()

    def validate_content_type(self, value):
        try:
            ContentType.objects.get(model=value)
        except ContentType.DoesNotExist:
            raise serializers.ValidationError(f"Invalid content type '{value}'.")
        return value

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