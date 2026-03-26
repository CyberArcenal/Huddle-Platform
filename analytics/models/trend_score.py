from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class ObjectTrendScore(models.Model):
    """
    Stores computed trending score for any content object.
    Useful for ranking posts in feeds without recalculating on every request.
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    score = models.FloatField(default=0.0)
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("content_type", "object_id")
        indexes = [
            models.Index(fields=["score"]),
            models.Index(fields=["calculated_at"]),
        ]

    def __str__(self):
        return f"{self.content_object} trending score: {self.score}"

