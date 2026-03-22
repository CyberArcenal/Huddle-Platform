



# feed/utils.py or inside reaction/views.py

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

def can_view_content(user, content_type: str, object_id: int) -> bool:
    """Check if a user is allowed to view a content object (for reactions)."""
    try:
        ct = ContentType.objects.get(model=content_type.lower())
    except ContentType.DoesNotExist:
        return False

    model_class = ct.model_class()
    try:
        obj = model_class.objects.get(pk=object_id)
    except model_class.DoesNotExist:
        return False

    # If the object is soft‑deleted, deny access
    if hasattr(obj, 'is_deleted') and obj.is_deleted:
        return False

    # If the object has a privacy field, apply the same rules as comments
    if hasattr(obj, 'privacy'):
        privacy = obj.privacy
        if privacy == 'public':
            return True
        if privacy == 'followers':
            owner = getattr(obj, 'user', None)
            if user.is_authenticated and owner and (user == owner or owner.followers.filter(id=user.id).exists()):
                return True
            return False
        if privacy == 'secret':
            owner = getattr(obj, 'user', None)
            return user.is_authenticated and user == owner

    # Default: assume public
    return True