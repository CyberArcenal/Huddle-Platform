from django.db import models
from django.conf import settings

# If Story is defined later or in another app, reference it by app_label.ModelName string:
# from stories.models import Story
# or use "stories.Story" below

class StoryHighlight(models.Model):
    """User-created collection of stories to feature on profile."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='story_highlights'
    )
    title = models.CharField(max_length=100, blank=True, default='')
    # Use SET_NULL so deleting the referenced Story won't delete the highlight
    cover = models.ForeignKey(
        'stories.Story',  # adjust app label if different; or use Story if imported
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='cover_for_highlights'
    )
    stories = models.ManyToManyField(
        'stories.Story',  # adjust app label if different
        related_name='highlights'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'story_highlights'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'title'], name='unique_user_highlight_title')
        ]

    def __str__(self):
        return f"{self.user.username}'s highlight: {self.title or 'Untitled'}"
