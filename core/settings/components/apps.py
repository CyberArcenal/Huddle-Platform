# Core Django + third-party apps
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.sites",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "qrcode",
    "celery",
    "django_celery_beat",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "cloudinary",
    "cloudinary_storage",
    "drf_spectacular",
]

# Project apps (single source of truth)
PROJECT_APPS = [
    "admin_pannel",
    "analytics",
    "events",
    "feed",
    "groups",
    "messaging",
    "notifications",
    "search",
    "stories",
    "dating",
    "users",
    "audit",
]

INSTALLED_APPS += PROJECT_APPS