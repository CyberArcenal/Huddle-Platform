
import logging
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction

from users.models.friendship import BlockedUser, MutedUser

logger = logging.getLogger(__name__)


# -----------------------------
# MUTED USER SIGNALS
# -----------------------------
@receiver(pre_save, sender=MutedUser)
def muted_user_pre_save(sender, instance, **kwargs):
    """Detect if a mute record is new or being updated."""
    if not instance.pk:
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    changes = {}
    if old_instance.muted_id != instance.muted_id:
        changes["muted"] = {"old": old_instance.muted_id, "new": instance.muted_id}

    if changes:
        instance._muted_changes = changes


@receiver(post_save, sender=MutedUser)
def muted_user_post_save(sender, instance, created, **kwargs):
    """Handle mute/unmute events."""
    if created:
        logger.info("User %s muted user %s", instance.user_id, instance.muted_id)
        # Example: send notification or audit log
        return

    if hasattr(instance, "_muted_changes"):
        def _handle_mute_changes():
            for field, change in instance._muted_changes.items():
                try:
                    logger.info(
                        "MutedUser change for id=%s field=%s old=%s new=%s",
                        instance.pk,
                        field,
                        change["old"],
                        change["new"],
                    )
                except Exception:
                    logger.exception("Error handling muted user change id=%s", instance.pk)

        try:
            transaction.on_commit(_handle_mute_changes)
        except Exception:
            _handle_mute_changes()

        del instance._muted_changes