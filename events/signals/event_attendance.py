from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from events.models import EventAttendance
from events.state_transition_service.event_attendance import EventAttendanceStateTransitionService


@receiver(pre_save, sender=EventAttendance)
def event_attendance_pre_save(sender, instance, **kwargs):
    """Detect status change before saving."""
    if not instance.pk:
        # New attendance record – no previous state
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    # Monitor status field
    if old_instance.status != instance.status:
        instance._state_transition_changes = {
            'status': {
                'old': old_instance.status,
                'new': instance.status
            }
        }


@receiver(post_save, sender=EventAttendance)
def event_attendance_post_save(sender, instance, created, **kwargs):
    """After save, handle status transition if any."""
    if created:
        # New attendance – initial status set; treat as a transition from None
        EventAttendanceStateTransitionService.handle_status_change(
            instance,
            old_status=None,
            new_status=instance.status
        )
        return

    if hasattr(instance, '_state_transition_changes'):
        changes = instance._state_transition_changes
        if 'status' in changes:
            change = changes['status']
            EventAttendanceStateTransitionService.handle_status_change(
                instance,
                change['old'],
                change['new']
            )
        del instance._state_transition_changes