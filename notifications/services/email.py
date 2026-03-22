import logging
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.template import Template, Context
from typing import List, Optional

logger = logging.getLogger(__name__)


class EmailService:
    """
    Service for sending emails with optional template rendering.
    """

    @staticmethod
    def send_simple_email(
        subject: str,
        message: str,
        recipient_list: List[str],
        from_email: Optional[str] = None,
        html_message: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Send a simple email using Django's send_mail.

        Args:
            subject: Email subject.
            message: Plain text message.
            recipient_list: List of recipient email addresses.
            from_email: Sender email (defaults to DEFAULT_FROM_EMAIL).
            html_message: Optional HTML version.
            **kwargs: Additional arguments passed to send_mail.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email or settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=False,
                **kwargs
            )
            logger.info(f"Email sent to {recipient_list}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_list}: {e}")
            return False

    @staticmethod
    def send_template_email(
        subject_template: str,
        body_template: str,
        context: dict,
        recipient_list: List[str],
        from_email: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Send an email rendered from Django templates.

        Args:
            subject_template: Template string for subject.
            body_template: Template string for body (can be plain or HTML).
            context: Dictionary of context variables.
            recipient_list: List of recipient emails.
            from_email: Sender email.
            **kwargs: Additional arguments.

        Returns:
            bool: Success status.
        """
        try:
            subject = Template(subject_template).render(Context(context))
            body = Template(body_template).render(Context(context))
            return EmailService.send_simple_email(
                subject=subject,
                message=body,
                recipient_list=recipient_list,
                from_email=from_email,
                **kwargs
            )
        except Exception as e:
            logger.error(f"Failed to send template email: {e}")
            return False

    @staticmethod
    def send_email_with_attachment(
        subject: str,
        message: str,
        recipient_list: List[str],
        attachment_path: str,
        from_email: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Send an email with a file attachment using Django's EmailMessage.

        Args:
            subject: Email subject.
            message: Email body.
            recipient_list: List of recipients.
            attachment_path: Path to file to attach.
            from_email: Sender email.
            **kwargs: Additional arguments.

        Returns:
            bool: Success status.
        """
        try:
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=from_email or settings.DEFAULT_FROM_EMAIL,
                to=recipient_list,
                **kwargs
            )
            email.attach_file(attachment_path)
            email.send(fail_silently=False)
            logger.info(f"Email with attachment sent to {recipient_list}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email with attachment: {e}")
            return False