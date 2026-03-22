from django.contrib.contenttypes.models import ContentType


# ---------------------------- Helpers ----------------------------
def get_content_object(content_type_name: str, object_id: int):
    """Retrieve a model instance by its content type name (e.g., 'post') and object ID."""
    try:
        content_type = ContentType.objects.get(model=content_type_name.lower())
    except ContentType.DoesNotExist:
        return None
    return content_type.get_object_for_this_type(pk=object_id)


def can_view_comments(user, obj) -> bool:
    """
    Determine if `user` is allowed to view comments on `obj`.
    Supports objects with a `privacy` field and optional `is_deleted`.
    """
    if obj is None:
        return False

    # If the object has an is_deleted flag and is deleted, deny access.
    if hasattr(obj, "is_deleted") and obj.is_deleted:
        return False

    # If the object doesn't have a privacy field, assume it's public.
    if not hasattr(obj, "privacy"):
        return True

    privacy = obj.privacy
    if privacy == "public":
        return True
    if privacy == "followers":
        # Check if the user follows the object's owner (if the object has a user/owner)
        # This is a simplistic example; adjust to your actual follower relationship.
        owner = getattr(obj, "user", None)
        if owner and user.is_authenticated:
            # Assume `owner.followers` is the reverse relation for followers.
            return user == owner or owner.followers.filter(id=user.id).exists()
        return False
    if privacy == "secret":
        owner = getattr(obj, "user", None)
        return user.is_authenticated and user == owner
    return False
