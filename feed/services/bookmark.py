from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from feed.models.bookmark import ObjectBookmark

class BookmarkService:
    # --- CRUD ---
    @staticmethod
    def add_bookmark(user, obj):
        """Add a bookmark for the given object."""
        ct = ContentType.objects.get_for_model(obj)
        bookmark, created = ObjectBookmark.objects.get_or_create(
            user=user,
            content_type=ct,
            object_id=obj.id,
        )
        return bookmark

    @staticmethod
    def remove_bookmark(user, obj):
        """Remove a bookmark if it exists."""
        ct = ContentType.objects.get_for_model(obj)
        ObjectBookmark.objects.filter(
            user=user,
            content_type=ct,
            object_id=obj.id,
        ).delete()

    @staticmethod
    def update_bookmark(user, obj, new_notes=None):
        """
        Update bookmark metadata (e.g., notes, tags).
        Extend ObjectBookmark model with extra fields if needed.
        """
        ct = ContentType.objects.get_for_model(obj)
        bookmark = ObjectBookmark.objects.filter(
            user=user,
            content_type=ct,
            object_id=obj.id,
        ).first()
        if bookmark and new_notes is not None:
            bookmark.notes = new_notes
            bookmark.save()
        return bookmark

    @staticmethod
    def get_bookmark(user, obj):
        """Retrieve a specific bookmark for a user/object."""
        ct = ContentType.objects.get_for_model(obj)
        return ObjectBookmark.objects.filter(
            user=user,
            content_type=ct,
            object_id=obj.id,
        ).first()

    # --- Stats ---
    @staticmethod
    def has_bookmarked(user, obj):
        """Check if the user bookmarked the object."""
        ct = ContentType.objects.get_for_model(obj)
        return ObjectBookmark.objects.filter(
            user=user,
            content_type=ct,
            object_id=obj.id,
        ).exists()

    @staticmethod
    def get_bookmark_count(obj):
        """Return total bookmarks for the object."""
        ct = ContentType.objects.get_for_model(obj)
        return ObjectBookmark.objects.filter(
            content_type=ct,
            object_id=obj.id,
        ).count()

    @staticmethod
    def get_user_bookmark_count(user):
        """Return total number of bookmarks created by a user."""
        return ObjectBookmark.objects.filter(user=user).count()

    @staticmethod
    def get_top_bookmarked_objects(limit=10):
        """
        Return the most bookmarked objects across all content types.
        Useful for analytics or trending feeds.
        """
        return (
            ObjectBookmark.objects.values("content_type", "object_id")
            .annotate(total=Count("id"))
            .order_by("-total")[:limit]
        )
