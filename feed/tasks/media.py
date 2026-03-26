# feed/tasks.py
from celery import shared_task
from PIL import Image
from django.core.files import File
import os

@shared_task
def generate_media_variants(media_id):
    from feed.models import Media
    media = Media.objects.get(id=media_id)

    # Buksan ang orihinal na file
    with Image.open(media.file) as img:
        width, height = img.size
        variants = {}

        # Gumawa ng thumbnail (150x150)
        thumb = img.copy()
        thumb.thumbnail((150, 150))
        thumb_path = f'media/variants/thumb_{media.id}.jpg'
        thumb.save(thumb_path)  # dapat i-save sa storage (hal. S3)
        variants['thumbnail'] = {
            'file': thumb_path,
            'width': thumb.width,
            'height': thumb.height,
        }

        # Gumawa ng small (480px width)
        # ... katulad na proseso

    # I-update ang metadata
    media.metadata.update({
        'original': {'width': width, 'height': height},
        'variants': variants,
        'processing_status': 'completed'
    })
    media.save()