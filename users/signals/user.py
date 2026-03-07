from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from users.models import User
from users.state_transition_service.user import UserStateTransitionService


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

    # List of fields we care about
    monitored_fields = ['status', 'is_active', 'is_verified', 'is_staff']
    changes = {}

    for field in monitored_fields:
        old_val = getattr(old_instance, field)
        new_val = getattr(instance, field)
        if old_val != new_val:
            changes[field] = {'old': old_val, 'new': new_val}

    if changes:
        # Attach changes to the instance so post_save can use them
        instance._state_transition_changes = changes


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """After save, handle state transitions if any."""
    if created:
        # Brand new user – handle creation
        UserStateTransitionService.handle_user_created(instance)
        return

    if hasattr(instance, '_state_transition_changes'):
        changes = instance._state_transition_changes
        for field, change in changes.items():
            # Dynamically call the appropriate handler method
            handler_name = f'handle_{field}_change'
            handler = getattr(UserStateTransitionService, handler_name, None)
            if handler:
                handler(instance, change['old'], change['new'])
        # Clean up to avoid leaking state
        del instance._state_transition_changes