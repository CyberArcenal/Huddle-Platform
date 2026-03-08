# core/email_backend.py
from django.core.mail.backends.smtp import EmailBackend
import logging

logger = logging.getLogger(__name__)

def get_dynamic_email_backend() -> EmailBackend:

    logger.debug(f"Email backend: {get_email_server()} {get_email_port()} {get_email_username()} {get_email_password()} {get_email_use_ssl()} {get_email_use_tls() }")
    return EmailBackend(
        host=get_email_server(),
        port=get_email_port(),
        username=get_email_username() or None,
        password=get_email_password() or None,
        use_tls=get_email_use_tls(),
        use_ssl=get_email_use_ssl(),
        timeout=30,
    )