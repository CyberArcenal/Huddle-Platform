from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from feed.models.bookmark import ObjectBookmark
import logging
from typing import Union, Optional

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)
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
    @transaction.atomic
    def remove_bookmark_by_target(user, content_type: Union[ContentType, str], object_id: int) -> int:
        """
        Remove bookmark(s) for a given user and target (content_type + object_id).

        Parameters
        - user: Django User instance performing the removal.
        - content_type: either a ContentType instance or a string in the form "app_label.model" or "model".
        - object_id: primary key of the target object (int or str that can be used in filter).

        Returns
        - int: number of Bookmark rows deleted (0 if none found).

        Behavior
        - If content_type is a string, it will be resolved to a ContentType.
        - Only bookmarks belonging to the provided user are removed.
        - The operation is atomic.
        - Does not raise if the target object itself no longer exists; it deletes bookmarks by content_type + object_id.
        """
        # Resolve ContentType if a string was provided
        ct: Optional[ContentType] = None
        try:
            if isinstance(content_type, ContentType):
                ct = content_type
            elif isinstance(content_type, str):
                if "." in content_type:
                    app_label, model = content_type.split(".", 1)
                    ct = ContentType.objects.get(app_label=app_label, model=model)
                else:
                    ct = ContentType.objects.get(model=content_type)
            else:
                raise ValueError("content_type must be a ContentType or string")
        except ContentType.DoesNotExist:
            logger.debug("remove_bookmark_by_target: invalid content_type %s", content_type)
            return 0
        except Exception as e:
            logger.exception("remove_bookmark_by_target: unexpected error resolving content_type: %s", e)
            raise

        # Delete bookmarks matching user + content_type + object_id
        try:
            qs = ObjectBookmark.objects.filter(user=user, content_type=ct, object_id=object_id)
            deleted_count, _ = qs.delete()
            if deleted_count:
                logger.info(
                    "Removed %d bookmark(s) for user=%s target=%s:%s",
                    deleted_count, getattr(user, "id", user), ct, object_id
                )
            else:
                logger.debug(
                    "No bookmarks found to remove for user=%s target=%s:%s",
                    getattr(user, "id", user), ct, object_id
                )
            return deleted_count
        except Exception as e:
            logger.exception(
                "Failed to remove bookmark(s) for user=%s target=%s:%s: %s",
                getattr(user, "id", user), ct, object_id, e
            )
            raise

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
