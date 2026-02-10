from django.conf import settings
from django.core.files.storage import default_storage

def get_absolute_media_url(path):
    """Generate absolute URL for media files"""
    if not path:
        return None
    return f"{settings.BASE_URL}{default_storage.url(path)}"