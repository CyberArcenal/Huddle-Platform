from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver

from audit.models.base import AuditLog

# This is a simplified example – you might need to capture old and new values.
@receiver(pre_save)
def log_model_change(sender, instance, **kwargs):
    # Avoid recursion on AuditLog itself
    if sender == AuditLog:
        return
    if not instance.pk:
        # New instance
        return
    # Get old instance
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    # You would need to determine which fields changed, and who the user is.
    # This is complex; better to call the service manually in views/services.
    pass

# Instead of signals, it's often simpler to call the audit service explicitly in views or services.