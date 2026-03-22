import os

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")


SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", 'support@example.com')
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
