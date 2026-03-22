import logging
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from notifications.models.email_template import EmailTemplate
from notifications.models.notify_log import NotifyLog
from notifications.services.email import EmailService
from notifications.services.push import PushService
from notifications.services.sms import SMSService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=NotifyLog)
def notifylog_post_save(sender, instance: NotifyLog, created: bool, **kwargs):
    """
    When a NotifyLog is created, send the actual notification via the specified channel.
    """
    if not created:
        return  # only send on new logs

    start_time = timezone.now()
    success = False
    error_message = None

    try:
        if instance.channel == "email":
            if instance.type and instance.type != "custom":
                from django.template import Template, Context
                from notifications.models.email_template import EmailTemplate

                try:
                    template = EmailTemplate.objects.get(name=instance.type)
                    context = Context(instance.metadata or {})
                    subject = Template(template.subject).render(context)
                    body = Template(template.content).render(context)

                    success = EmailService.send_simple_email(
                        subject=subject,
                        message=body,
                        recipient_list=[instance.recipient_email],
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        html_message=body,
                    )

                    # ✅ Save the rendered subject/body for audit
                    instance.subject = subject
                    instance.payload = body

                except EmailTemplate.DoesNotExist:
                    logger.error(f"No template found for type={instance.type}")
                    success = False
                    error_message = f"No template found for type={instance.type}"
            else:
                success = EmailService.send_simple_email(
                    subject=instance.subject,
                    message=instance.payload or "",
                    recipient_list=[instance.recipient_email],
                    from_email=settings.DEFAULT_FROM_EMAIL,
                )

        elif instance.channel == "sms":
            # Assuming recipient_email contains phone number for SMS
            success = SMSService.send_sms(
                to_number=instance.recipient_email,
                message=instance.payload or "",
            )
        elif instance.channel == "push":
            # For push, we need a device token; assuming instance.recipient_email
            # contains a user identifier or token.
            success = PushService.send_push(
                recipient_id=instance.recipient_email,
                title=instance.subject or "Notification",
                message=instance.payload or "",
                data={},  # optional metadata
            )
        else:
            logger.warning(
                f"Unknown channel '{instance.channel}' for NotifyLog {instance.id}"
            )
            success = False
            error_message = f"Unknown channel: {instance.channel}"

    except Exception as e:
        logger.exception(f"Error sending notification for log {instance.id}")
        success = False
        error_message = str(e)

    # Update the log entry
    end_time = timezone.now()
    instance.duration_ms = int((end_time - start_time).total_seconds() * 1000)

    if success:
        instance.status = "sent"
        instance.sent_at = end_time
    else:
        instance.status = "failed"
        instance.error_message = error_message or "Unknown error"
        instance.last_error_at = end_time

    instance.save(
        update_fields=[
            "status",
            "sent_at",
            "error_message",
            "last_error_at",
            "duration_ms",
            "subject",
            "payload",
        ]
    )
