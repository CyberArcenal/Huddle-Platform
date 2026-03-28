import logging
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction
from users.models import User
from users.state_transition_service.user import UserStateTransitionService

logger = logging.getLogger(__name__)

@receiver(pre_save, sender=User)
def user_pre_save(sender, instance, **kwargs):
    """Detect changes to monitored fields before saving."""
    if not instance.pk:
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    monitored_fields = ["status", "is_active", "is_verified", "is_staff"]
    changes = {}

    for field in monitored_fields:
        old_val = getattr(old_instance, field)
        new_val = getattr(instance, field)
        if old_val != new_val:
            changes[field] = {"old": old_val, "new": new_val}

    if changes:
        instance._state_transition_changes = changes


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """After save, handle state transitions."""
    if created:
        try:
            UserStateTransitionService.handle_user_created(instance)
        except Exception:
            logger.exception(
                "Error handling user created transition for user_id=%s", instance.pk
            )
        return

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
        del instance._state_transition_changes