from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from feed.models import Post
from feed.state_transition_service.post import PostStateTransitionService


@receiver(pre_save, sender=Post)
def post_pre_save(sender, instance, **kwargs):
    """Detect is_deleted change before saving."""
    if not instance.pk:
        # New post – no previous state
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    # Monitor is_deleted field
    if old_instance.is_deleted != instance.is_deleted:
        instance._state_transition_changes = {
            'is_deleted': {
                'old': old_instance.is_deleted,
                'new': instance.is_deleted
            }
        }


@receiver(post_save, sender=Post)
def post_post_save(sender, instance, created, **kwargs):
    """After save, handle is_deleted transition if any."""
    if created:
        # New post – maybe log creation, but no transition needed here.
        return

    if hasattr(instance, '_state_transition_changes'):
        changes = instance._state_transition_changes
        if 'is_deleted' in changes:
            change = changes['is_deleted']
            PostStateTransitionService.handle_is_deleted_change(
                instance,
                change['old'],
                change['new']
            )
        del instance._state_transition_changes