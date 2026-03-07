from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from admin_pannel.models import ReportedContent
from admin_pannel.state_transition_service.reported_content import ReportedContentStateTransitionService


@receiver(pre_save, sender=ReportedContent)
def reported_content_pre_save(sender, instance, **kwargs):
    """Detect status change before saving."""
    if not instance.pk:
        # New report – no previous state
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    # Only monitor the 'status' field
    if old_instance.status != instance.status:
        instance._state_transition_changes = {
            'status': {
                'old': old_instance.status,
                'new': instance.status
            }
        }


@receiver(post_save, sender=ReportedContent)
def reported_content_post_save(sender, instance, created, **kwargs):
    """After save, handle status transition if any."""
    if created:
        # New report – maybe log creation or update counts?
        ReportedContentStateTransitionService.handle_report_created(instance)
        return

    if hasattr(instance, '_state_transition_changes'):
        changes = instance._state_transition_changes
        status_change = changes.get('status')
        if status_change:
            ReportedContentStateTransitionService.handle_status_change(
                instance,
                status_change['old'],
                status_change['new']
            )
        del instance._state_transition_changes