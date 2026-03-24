from typing import List, Optional
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction
from stories.models import StoryHighlight, Story
from users.models import User

class StoryHighlightService:
    @staticmethod
    def create_highlight(user: User, title: str, story_ids: List[int]) -> StoryHighlight:
        """Create a new highlight with given stories."""
        if not title:
            raise ValidationError("Title is required.")
        if StoryHighlight.objects.filter(user=user, title=title).exists():
            raise ValidationError("You already have a highlight with that title.")

        stories = Story.objects.filter(id__in=story_ids, user=user)
        if len(stories) != len(story_ids):
            raise ValidationError("One or more stories are invalid or do not belong to you.")

        with transaction.atomic():
            highlight = StoryHighlight.objects.create(user=user, title=title)
            highlight.stories.set(stories)
        return highlight

    @staticmethod
    def update_highlight(highlight: StoryHighlight, title: Optional[str] = None, story_ids: Optional[List[int]] = None) -> StoryHighlight:
        """Update highlight title or stories."""
        if title is not None:
            if StoryHighlight.objects.filter(user=highlight.user, title=title).exclude(id=highlight.id).exists():
                raise ValidationError("Another highlight with that title already exists.")
            highlight.title = title
            highlight.save()

        if story_ids is not None:
            stories = Story.objects.filter(id__in=story_ids, user=highlight.user)
            if len(stories) != len(story_ids):
                raise ValidationError("One or more stories are invalid or do not belong to you.")
            highlight.stories.set(stories)

        return highlight

    @staticmethod
    def delete_highlight(highlight: StoryHighlight) -> bool:
        """Delete a highlight."""
        try:
            highlight.delete()
            return True
        except Exception:
            return False

    @staticmethod
    def get_user_highlights(user: User) -> List[StoryHighlight]:
        """Get all highlights for a user."""
        return list(user.story_highlights.all())

    @staticmethod
    def add_stories_to_highlight(highlight: StoryHighlight, story_ids: List[int]) -> StoryHighlight:
        """Add stories to an existing highlight (without removing existing)."""
        stories = Story.objects.filter(id__in=story_ids, user=highlight.user)
        if len(stories) != len(story_ids):
            raise ValidationError("One or more stories are invalid or do not belong to you.")
        highlight.stories.add(*stories)
        return highlight

    @staticmethod
    def remove_stories_from_highlight(highlight: StoryHighlight, story_ids: List[int]) -> StoryHighlight:
        """Remove stories from a highlight."""
        stories = Story.objects.filter(id__in=story_ids, user=highlight.user)
        highlight.stories.remove(*stories)
        return highlight
    @staticmethod
    def set_highlight_cover(highlight: StoryHighlight, user: User, cover_story_id: int) -> StoryHighlight:
        """
        Set the cover story for a highlight.
        Raises PermissionDenied if user is not owner.
        Raises ObjectDoesNotExist if story not found or not part of highlight.
        Raises ValidationError for invalid input.
        """
        if cover_story_id is None or cover_story_id <= 0:
            raise ValidationError("Invalid cover_story_id.")

        if highlight.user_id != getattr(user, "id", None):
            raise PermissionDenied("You do not have permission to modify this highlight.")

        try:
            story = Story.objects.get(id=cover_story_id, user=user)
        except Story.DoesNotExist:
            raise ObjectDoesNotExist("Story not found or does not belong to the user.")

        if not highlight.stories.filter(id=story.id).exists():
            raise ObjectDoesNotExist("Story is not part of this highlight.")

        with transaction.atomic():
            highlight.cover = story
            highlight.save(update_fields=["cover"])
            highlight.refresh_from_db()
        return highlight