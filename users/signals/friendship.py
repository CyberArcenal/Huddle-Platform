import logging
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction

from users.models.friendship import Friendship

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Friendship)
def friendship_pre_save(sender, instance, **kwargs):
    """Detect changes to monitored fields before saving."""
    if not instance.pk:
        # New friendship – no previous state to compare
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    monitored_fields = ["status", "tag"]
    changes = {}

    for field in monitored_fields:
        old_val = getattr(old_instance, field)
        new_val = getattr(instance, field)
        if old_val != new_val:
            changes[field] = {"old": old_val, "new": new_val}

    if changes:
        # Attach changes to the instance so post_save can use them
        instance._friendship_changes = changes


@receiver(post_save, sender=Friendship)
def friendship_post_save(sender, instance, created, **kwargs):
    """After save, handle state transitions and tag changes."""
    if created:
        # Brand new friendship request
        logger.info(
            "New friendship request created: from_user=%s to_user=%s status=%s",
            instance.user_id,
            instance.friend_id,
            instance.status,
        )
        return

    if hasattr(instance, "_friendship_changes"):
        changes = instance._friendship_changes

        def _handle_changes():
            for field, change in changes.items():
                try:
                    if field == "status":
                        logger.info(
                            "Friendship status changed for friendship_id=%s: %s -> %s",
                            instance.pk,
                            change["old"],
                            change["new"],
                        )
                        # Example: send notification when accepted
                        if change["new"] == "accepted":
                            # call your notification service here
                            pass

                    elif field == "tag":
                        logger.info(
                            "Friendship tag changed for friendship_id=%s: %s -> %s",
                            instance.pk,
                            change["old"],
                            change["new"],
                        )
                        # Example: create system post or audit log
                        pass

                except Exception:
                    logger.exception(
                        "Error handling friendship change field=%s friendship_id=%s",
                        field,
                        instance.pk,
                    )

        try:
            transaction.on_commit(_handle_changes)
        except Exception:
            # fallback: run immediately
            try:
                _handle_changes()
            except Exception:
                logger.exception(
                    "Fallback: failed to handle friendship changes friendship_id=%s",
                    instance.pk,
                )

        # cleanup
        del instance._friendship_changes