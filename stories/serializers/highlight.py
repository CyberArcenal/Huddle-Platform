from typing import List
from rest_framework import serializers
from django.shortcuts import get_list_or_404

from stories.models import StoryHighlight, Story
from stories.serializers.story import StorySerializer
from users.serializers.user.minimal import UserMinimalSerializer


class StoryHighlightSerializer(serializers.ModelSerializer):
    user = UserMinimalSerializer(read_only=True)
    stories = StorySerializer(many=True, read_only=True)
    story_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = StoryHighlight
        fields = [
            "id",
            "user",
            "title",
            "cover_url",
            "stories",
            "story_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def get_story_count(self, obj: StoryHighlight) -> int:
        return obj.stories.count()

    def get_cover_url(self, obj: StoryHighlight) -> str:
        cover = getattr(obj, "cover", None)
        if not cover:
            return None
        # Use media_url field from Story model
        media = getattr(cover, "media_url", None)
        if media and getattr(media, "url", None):
            return media.url
        # Fallback to content for text stories
        if getattr(cover, "content", None):
            return None
        return None


class StoryHighlightCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=100, allow_blank=True)
    story_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)

    def validate_story_ids(self, value: List[int]) -> List[int]:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError("Authentication required to create highlight.")

        # Ensure all story ids exist and belong to the requesting user
        stories_qs = Story.objects.filter(id__in=value, user=user)
        if stories_qs.count() != len(set(value)):
            raise serializers.ValidationError("One or more story_ids are invalid or do not belong to the user.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        title = validated_data.get("title", "")
        story_ids = validated_data["story_ids"]

        highlight = StoryHighlight.objects.create(user=user, title=title)
        highlight.stories.set(Story.objects.filter(id__in=story_ids, user=user))

        # Optionally set the first story as cover if none provided
        if story_ids:
            first_story = Story.objects.filter(id=story_ids[0], user=user).first()
            if first_story:
                highlight.cover = first_story
                highlight.save(update_fields=["cover"])
        return highlight


class StoryHighlightUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=100, required=False, allow_blank=True)
    story_ids = serializers.ListField(child=serializers.IntegerField(), required=False)

    def validate_story_ids(self, value: List[int]) -> List[int]:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError("Authentication required to update highlight.")

        stories_qs = Story.objects.filter(id__in=value, user=user)
        if stories_qs.count() != len(set(value)):
            raise serializers.ValidationError("One or more story_ids are invalid or do not belong to the user.")
        return value

    def update(self, instance: StoryHighlight, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        title = validated_data.get("title", None)
        story_ids = validated_data.get("story_ids", None)

        if title is not None:
            instance.title = title

        if story_ids is not None:
            instance.stories.set(Story.objects.filter(id__in=story_ids, user=user))
            # If current cover is not in new set, reset cover to first story or null
            if instance.cover and instance.cover.id not in story_ids:
                new_cover = Story.objects.filter(id__in=story_ids, user=user).first()
                instance.cover = new_cover

        instance.save()
        return instance


class StoryHighlightAddStoriesSerializer(serializers.Serializer):
    story_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)

    def validate_story_ids(self, value: List[int]) -> List[int]:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError("Authentication required to add stories.")

        stories_qs = Story.objects.filter(id__in=value, user=user)
        if stories_qs.count() != len(set(value)):
            raise serializers.ValidationError("One or more story_ids are invalid or do not belong to the user.")
        return value

    def save(self, highlight: StoryHighlight):
        story_ids = self.validated_data["story_ids"]
        request = self.context.get("request")
        user = getattr(request, "user", None)
        highlight.stories.add(*Story.objects.filter(id__in=story_ids, user=user))
        return highlight


class StoryHighlightRemoveStoriesSerializer(serializers.Serializer):
    story_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)

    def validate_story_ids(self, value: List[int]) -> List[int]:
        # Allow removing ids even if some are not present; no strict ownership check here
        return value

    def save(self, highlight: StoryHighlight):
        story_ids = self.validated_data["story_ids"]
        highlight.stories.remove(*Story.objects.filter(id__in=story_ids))
        # If cover was removed, reset cover to first remaining story or null
        if highlight.cover and highlight.cover.id in story_ids:
            remaining = highlight.stories.first()
            highlight.cover = remaining
            highlight.save(update_fields=["cover"])
        return highlight

class StoryHighlightSetCoverSerializer(serializers.Serializer):
    cover_story_id = serializers.IntegerField()

    def validate_cover_story_id(self, value):
        # optional: additional validation can be done in service layer
        if value <= 0:
            raise serializers.ValidationError("Invalid story id.")
        return value