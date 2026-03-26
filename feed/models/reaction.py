from django.conf import settings
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class ReactionType(models.TextChoices):
    LIKE = "like", "Like"
    DISLIKE = "dislike", "Dislike"
    LOVE = "love", "Love"
    CARE = "care", "Care"
    HAHA = "haha", "Haha"
    WOW = "wow", "Wow"
    SAD = "sad", "Sad"
    ANGRY = "angry", "Angry"

REACTION_TYPES = [(tag.value, tag.label) for tag in ReactionType]  # keep for choices

class Reaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reactions')
    
    # Generic relation to any content object
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    reaction_type = models.CharField(max_length=10, choices=REACTION_TYPES, default=ReactionType.LIKE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'likes'  # keep existing table name
        unique_together = ('user', 'content_type', 'object_id')
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]