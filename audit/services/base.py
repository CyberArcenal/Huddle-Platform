import json
from django.contrib.auth import get_user_model
from django.utils import timezone

from audit.models.base import AuditLog

User = get_user_model()

class AuditService:
    """Service to log actions in the system."""

    @staticmethod
    def log_action(user, action, model, record_id=None, old_data=None, new_data=None,
                   ip_address=None, message='', **extra):
        """Generic audit log method."""
        AuditLog.objects.create(
            user=user,
            action=action,
            model_name=model._meta.label if hasattr(model, '_meta') else str(model),
            record_id=str(record_id) if record_id is not None else None,
            old_data=old_data or {},
            new_data=new_data or {},
            ip_address=ip_address,
            message=message,
            **extra
        )

    @staticmethod
    def log_create(user, instance, ip_address=None, message=''):
        """Log creation of an instance."""
        # Convert instance to dict (exclude fields like password)
        data = AuditService._instance_to_dict(instance)
        AuditService.log_action(
            user=user,
            action='CREATE',
            model=instance,
            record_id=instance.pk,
            new_data=data,
            ip_address=ip_address,
            message=message
        )

    @staticmethod
    def log_update(user, instance, old_data, new_data, ip_address=None, message=''):
        """Log update of an instance."""
        # Convert to dict if not already
        if not isinstance(old_data, dict):
            old_data = AuditService._instance_to_dict(instance, fields=old_data)
        if not isinstance(new_data, dict):
            new_data = AuditService._instance_to_dict(instance, fields=new_data)
        AuditService.log_action(
            user=user,
            action='UPDATE',
            model=instance,
            record_id=instance.pk,
            old_data=old_data,
            new_data=new_data,
            ip_address=ip_address,
            message=message
        )

    @staticmethod
    def log_delete(user, instance, ip_address=None, message=''):
        """Log deletion of an instance."""
        data = AuditService._instance_to_dict(instance)
        AuditService.log_action(
            user=user,
            action='DELETE',
            model=instance,
            record_id=instance.pk,
            old_data=data,
            ip_address=ip_address,
            message=message
        )

    @staticmethod
    def _instance_to_dict(instance, exclude=None):
        """Convert model instance to dict suitable for JSON."""
        if exclude is None:
            exclude = []
        data = {}
        for field in instance._meta.get_fields():
            if field.name in exclude:
                continue
            value = getattr(instance, field.name)
            if hasattr(value, 'strftime'):  # datetime
                value = value.isoformat()
            elif isinstance(value, (list, dict, int, float, str, bool, type(None))):
                pass  # already serializable
            else:
                value = str(value)  # fallback
            data[field.name] = value
        return data