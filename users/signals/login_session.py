from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from users.models import LoginSession
from users.state_transition_service.login_session import LoginSessionStateTransitionService


@receiver(pre_save, sender=LoginSession)
def login_session_pre_save(sender, instance, **kwargs):
    """Detect is_active change before saving."""
    if not instance.pk:
        # New session – no previous state
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    # Monitor is_active field
    if old_instance.is_active != instance.is_active:
        instance._state_transition_changes = {
            'is_active': {
                'old': old_instance.is_active,
                'new': instance.is_active
            }
        }


@receiver(post_save, sender=LoginSession)
def login_session_post_save(sender, instance, created, **kwargs):
    """After save, handle is_active transition if any."""
    if created:
        # New session – no deactivation here.
        return

    if hasattr(instance, '_state_transition_changes'):
        changes = instance._state_transition_changes
        if 'is_active' in changes:
            change = changes['is_active']
            # Only handle deactivation (True → False)
            if change['old'] is True and change['new'] is False:
                LoginSessionStateTransitionService.handle_session_deactivated(instance)
        del instance._state_transition_changes