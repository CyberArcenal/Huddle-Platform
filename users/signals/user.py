import logging
import os
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction
from feed.models.post import POST_TYPES, Post
from feed.services.post import PostService
from users.models import User
from users.state_transition_service.user import UserStateTransitionService

logger = logging.getLogger(__name__)


def _file_identifier(file_field):
    """
    Return a stable identifier for a FileField-like object to compare changes.
    Prefer name, then url, then str(file_field).
    """
    if not file_field:
        return None
    # FileField has .name; if using storages, .url may be available
    name = getattr(file_field, "name", None)
    if name:
        return name
    url = getattr(file_field, "url", None)
    if url:
        return url
    return str(file_field)


@receiver(pre_save, sender=User)
def user_pre_save(sender, instance, **kwargs):
    """Detect changes to monitored fields before saving."""
    if not instance.pk:
        # New user – no previous state to compare
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    # existing monitored fields (state transitions)
    monitored_fields = ["status", "is_active", "is_verified", "is_staff"]
    changes = {}

    for field in monitored_fields:
        old_val = getattr(old_instance, field)
        new_val = getattr(instance, field)
        if old_val != new_val:
            changes[field] = {"old": old_val, "new": new_val}

    # media fields to watch for profile/cover changes
    media_fields = ["profile_picture", "cover_photo"]
    media_changes = []

    for field in media_fields:
        old_file = getattr(old_instance, field, None)
        new_file = getattr(instance, field, None)

        old_id = _file_identifier(old_file)
        new_id = _file_identifier(new_file)

        if old_id != new_id:
            media_changes.append(
                {
                    "field": field,
                    "old": old_id,
                    "new": new_id,
                }
            )

    if changes:
        # Attach changes to the instance so post_save can use them
        instance._state_transition_changes = changes

    if media_changes:
        # Attach media changes for post_save
        instance._media_changes = media_changes


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """After save, handle state transitions and media-change system posts."""
    if created:
        # Brand new user – handle creation
        try:
            UserStateTransitionService.handle_user_created(instance)
        except Exception:
            logger.exception(
                "Error handling user created transition for user_id=%s", instance.pk
            )
        return

    # handle state transitions (existing behavior)
    if hasattr(instance, "_state_transition_changes"):
        changes = instance._state_transition_changes
        for field, change in changes.items():
            handler_name = f"handle_{field}_change"
            handler = getattr(UserStateTransitionService, handler_name, None)
            if handler:
                try:
                    handler(instance, change["old"], change["new"])
                except Exception:
                    logger.exception(
                        "Error handling state transition %s for user_id=%s",
                        field,
                        instance.pk,
                    )
        # Clean up to avoid leaking state
        del instance._state_transition_changes

    # handle media changes: create system posts after commit
    if hasattr(instance, "_media_changes"):
        media_changes = instance._media_changes

        def _create_media_posts():
            for change in media_changes:
                try:
                    field = change["field"]
                    # friendly label
                    if field == "profile_picture":
                        verb = "updated their profile picture"
                    elif field == "cover_photo":
                        verb = "updated their cover photo"
                    else:
                        verb = f"updated {field}"

                    display_name = getattr(instance, "get_full_name", None)
                    display_name = (
                        display_name()
                        if callable(display_name)
                        else (instance.username or "A user")
                    )
                    system_content = f"{display_name} {verb}."

                    # choose post_type safely
                    post_type = "system"
                    try:
                        valid_types = [choice[0] for choice in POST_TYPES]
                    except Exception:
                        valid_types = []

                    if post_type not in valid_types:
                        post_type = "text"

                    # attach media if available (pass FileField-like object)
                    media = None
                    file_obj = getattr(instance, field, None)
                    if file_obj:
                        media = [file_obj]

                    # create post (non-blocking)
                    try:
                        PostService.create_post(
                            user=instance,
                            content=system_content,
                            post_type=post_type,
                            media_files=media,
                            privacy="public",
                        )
                    except Exception:
                        # log but continue with other changes
                        logger.exception(
                            "Failed to create system post for user_id=%s field=%s",
                            instance.pk,
                            field,
                        )
                except Exception:
                    logger.exception(
                        "Unexpected error while creating media post for user_id=%s",
                        instance.pk,
                    )

        # schedule after commit
        try:
            transaction.on_commit(_create_media_posts)
        except Exception:
            # fallback: try immediately but swallow errors
            try:
                _create_media_posts()
            except Exception:
                logger.exception(
                    "Fallback: failed to create media posts for user_id=%s", instance.pk
                )

        # cleanup
        del instance._media_changes
