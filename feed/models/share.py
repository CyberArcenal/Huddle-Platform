from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from users.models import User


class Share(models.Model):
    """
    Represents a share action performed by a user on any content object.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shares')
    
    
    
    # Generic relation to the shared object
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    
    caption = models.TextField(blank=True, help_text="Optional message when sharing")
    privacy = models.CharField(
        max_length=10,
        choices=[
            ('public', 'Public'),
            ('followers', 'Followers'),
            ('private', 'Private (only me)')
        ],
        default='public'
    )
    
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shares'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"Share {self.id} by {self.user.username} of {self.content_type} #{self.object_id}"