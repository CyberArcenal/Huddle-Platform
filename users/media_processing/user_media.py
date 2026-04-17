import os
import logging
from io import BytesIO
import threading
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from users.models import UserImage

logger = logging.getLogger(__name__)


class UserMediaProcessingService:
    """Handle processing of user profile/cover images: generate variants and compress original."""

    @staticmethod
    def process_image(user_image: UserImage):
        """Generate variants (thumbnail, small, medium), then compress original image."""
        try:
            # Open original image
            with user_image.image.open("rb") as f:
                with Image.open(f) as img:
                    # Original metadata
                    width, height = img.size
                    img_format = img.format
                    original_size = user_image.image.size

                    metadata = {
                        'original': {
                            'width': width,
                            'height': height,
                            'format': img_format,
                            'size_bytes': original_size,
                            'type': user_image.image_type,
                        },
                        'variants': {},
                    }

                    # Define sizes for variants
                    sizes = {
                        'thumbnail': (150, 150),
                        'small': (480, 480),
                        'medium': (1024, 1024),
                    }

                    # Generate variants (using original high-res image)
                    for name, (max_w, max_h) in sizes.items():
                        img_copy = img.copy()
                        img_copy.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

                        buffer = BytesIO()
                        img_copy.save(buffer, format=img_format, quality=85)
                        buffer.seek(0)

                        base, ext = os.path.splitext(user_image.image.name)
                        variant_name = f"{base}_{name}{ext}"

                        variant_path = default_storage.save(
                            variant_name, ContentFile(buffer.read())
                        )

                        metadata['variants'][name] = {
                            'file': variant_path,
                            'width': img_copy.width,
                            'height': img_copy.height,
                            'size_bytes': default_storage.size(variant_path),
                        }

                    # ===== COMPRESS ORIGINAL IMAGE =====
                    # Get settings (with defaults)
                    max_dim = getattr(settings, "USER_IMAGE_MAX_DIMENSION", 1080)
                    quality = getattr(settings, "USER_IMAGE_COMPRESSION_QUALITY", 80)

                    # Create a copy for compression
                    compressed_img = img.copy()
                    if max(compressed_img.size) > max_dim:
                        compressed_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                    # Save compressed image to buffer
                    buffer = BytesIO()
                    # Use original format or fallback to JPEG for better compression
                    save_format = img_format if img_format in ['JPEG', 'PNG', 'WEBP'] else 'JPEG'
                    if save_format == 'JPEG':
                        compressed_img.save(buffer, format=save_format, quality=quality, optimize=True)
                    else:
                        compressed_img.save(buffer, format=save_format, optimize=True)
                    buffer.seek(0)

                    # Replace original file
                    original_name = user_image.image.name
                    user_image.image.delete(save=False)  # delete old file from storage
                    new_file = ContentFile(buffer.read())
                    user_image.image.save(original_name, new_file, save=False)

                    # Update metadata to reflect compressed original
                    metadata['original'] = {
                        'width': compressed_img.width,
                        'height': compressed_img.height,
                        'format': save_format,
                        'size_bytes': user_image.image.size,
                        'type': user_image.image_type,
                        'compressed': True,
                        'original_size_bytes': original_size,
                    }

                    user_image.caption = user_image.caption or ""
                    user_image.metadata = metadata
                    user_image.save(update_fields=['metadata', 'image'])

                    logger.info(
                        f"Processed and compressed user image {user_image.id} "
                        f"({user_image.image_type}) from {original_size} to {user_image.image.size} bytes"
                    )

        except Exception as e:
            logger.exception(f"Failed to process user image {user_image.id}: {e}")


def trigger_user_image_processing(user_image: UserImage):
    """
    Process user image asynchronously.
    """
    use_celery = getattr(settings, 'USER_MEDIA_USE_CELERY', False)

    if use_celery:
        try:
            from users.tasks.user_media import process_user_image_task
            process_user_image_task.delay(user_image.id)
            logger.debug(f"Scheduled user image processing via Celery for {user_image.id}")
            return
        except Exception as e:
            logger.warning(f"Celery not available: {e}, falling back to threading")

    threading.Thread(
        target=UserMediaProcessingService.process_image,
        args=(user_image,)
    ).start()
    logger.debug(f"Scheduled user image processing via threading for {user_image.id}")