INSTALLED_APPS = [
    # "daphne",
    # "channels",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.sites",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
]

INSTALLED_APPS += [
    "admin_pannel",
    "analytics",
    "events",
    "feed",
    "groups",
    "messaging",
    "notifications",
    "search",
    "stories",
    "users",
]

INSTALLED_APPS += [
    "qrcode",
    "celery",
    "django_celery_beat",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "cloudinary",
    "cloudinary_storage",
    "drf_spectacular",
]
