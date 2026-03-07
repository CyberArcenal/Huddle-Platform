from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from users.models import LoginCheckpoint
from users.state_transition_service.login_checkpoint import LoginCheckpointStateTransitionService


@receiver(pre_save, sender=LoginCheckpoint)
def login_checkpoint_pre_save(sender, instance, **kwargs):
    """Detect is_used change before saving."""
    if not instance.pk:
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    if old_instance.is_used != instance.is_used:
        instance._state_transition_changes = {
            'is_used': {
                'old': old_instance.is_used,
                'new': instance.is_used
            }
        }


@receiver(post_save, sender=LoginCheckpoint)
def login_checkpoint_post_save(sender, instance, created, **kwargs):
    """After save, handle is_used transition if any."""
    if created:
        return

    if hasattr(instance, '_state_transition_changes'):
        changes = instance._state_transition_changes
        if 'is_used' in changes:
            change = changes['is_used']
            if change['old'] is False and change['new'] is True:
                LoginCheckpointStateTransitionService.handle_checkpoint_used(instance)
        del instance._state_transition_changes