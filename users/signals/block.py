import logging
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction

from users.models.friendship import BlockedUser

logger = logging.getLogger(__name__)


# -----------------------------
# BLOCKED USER SIGNALS
# -----------------------------
@receiver(pre_save, sender=BlockedUser)
def blocked_user_pre_save(sender, instance, **kwargs):
    """Detect if a block record is new or being updated."""
    if not instance.pk:
        # New block – no previous state
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    changes = {}
    if old_instance.blocked_id != instance.blocked_id:
        changes["blocked"] = {"old": old_instance.blocked_id, "new": instance.blocked_id}

    if changes:
        instance._blocked_changes = changes


@receiver(post_save, sender=BlockedUser)
def blocked_user_post_save(sender, instance, created, **kwargs):
    """Handle block/unblock events."""
    if created:
        logger.info("User %s blocked user %s", instance.user_id, instance.blocked_id)
        # Example: send notification or audit log
        return

    if hasattr(instance, "_blocked_changes"):
        def _handle_block_changes():
            for field, change in instance._blocked_changes.items():
                try:
                    logger.info(
                        "BlockedUser change for id=%s field=%s old=%s new=%s",
                        instance.pk,
                        field,
                        change["old"],
                        change["new"],
                    )
                except Exception:
                    logger.exception("Error handling blocked user change id=%s", instance.pk)

        try:
            transaction.on_commit(_handle_block_changes)
        except Exception:
            _handle_block_changes()

        del instance._blocked_changes


