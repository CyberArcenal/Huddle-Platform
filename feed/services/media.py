import json
import os
import logging
from io import BytesIO
import subprocess
import threading
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from feed.models import Media
from feed.models.media import MediaVariant


logger = logging.getLogger(__name__)


class MediaProcessingService:
    """Handle processing of media files: generate variants, extract metadata."""

    @staticmethod
    def process_image(media: Media):
        """Generate thumbnails and resized versions for an image."""
        try:
            with Image.open(media.file) as img:
                # Original metadata (store in media.metadata)
                width, height = img.size
                img_format = img.format
                media.metadata = {
                    'original': {
                        'width': width,
                        'height': height,
                        'format': img_format,
                        'size_bytes': media.file.size,
                    },
                    'variants': {},  # will be filled with variant references
                }

                # Define sizes and variant types
                sizes = {
                    'thumbnail': (150, 150),
                    'small': (480, 480),
                    'medium': (1024, 1024),
                }

                # Base filename without extension, used for variant naming
                base_filename = os.path.splitext(os.path.basename(media.file.name))[0]
                ext = os.path.splitext(media.file.name)[1].lower()

                for variant_type, (max_width, max_height) in sizes.items():
                    # Create resized copy
                    img_copy = img.copy()
                    img_copy.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                    # Save to buffer
                    buffer = BytesIO()
                    img_copy.save(buffer, format=img_format, quality=85)
                    buffer.seek(0)

                    # Generate variant filename
                    variant_name = f"{base_filename}_{variant_type}{ext}"
                    content_file = ContentFile(buffer.read())

                    # Get or create variant record
                    variant, created = MediaVariant.objects.get_or_create(
                        media=media,
                        variant_type=variant_type,
                        defaults={
                            'width': img_copy.width,
                            'height': img_copy.height,
                            'size_bytes': len(content_file),
                        }
                    )

                    # If updating, delete old file first
                    if not created and variant.file:
                        variant.file.delete(save=False)

                    # Save the new file
                    variant.file.save(variant_name, content_file)

                    # Update fields that might have changed (e.g., size)
                    variant.width = img_copy.width
                    variant.height = img_copy.height
                    variant.size_bytes = len(content_file)
                    variant.save()

                    # Store reference in media.metadata for backward compatibility
                    media.metadata['variants'][variant_type] = {
                        'file': variant.file.name,
                        'width': variant.width,
                        'height': variant.height,
                        'size_bytes': variant.size_bytes,
                    }

                media.save(update_fields=['metadata'])
                logger.info(f"Processed image media {media.id}")

        except Exception as e:
            logger.exception(f"Failed to process image media {media.id}: {e}")

    @staticmethod
    def process_video(media: Media):
        """Extract thumbnail and video metadata."""
        try:
            # Reuse the extract_thumbnail helper
            from feed.utils.media import extract_thumbnail
            thumbnail_file, tmp_path = extract_thumbnail(media.file, time='00:00:01')

            # Get video metadata using ffprobe
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'stream=width,height,duration,codec_name',
                '-of', 'json',
                media.file.path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), {})

            # Store original metadata in media.metadata
            media.metadata = {
                'original': {
                    'width': video_stream.get('width'),
                    'height': video_stream.get('height'),
                    'duration': float(video_stream.get('duration', 0)),
                    'codec': video_stream.get('codec_name'),
                },
                'variants': {},
            }

            # Generate variant filename for thumbnail
            base_filename = os.path.splitext(os.path.basename(media.file.name))[0]
            variant_name = f"{base_filename}_thumbnail.jpg"

            # Get or create thumbnail variant
            variant, created = MediaVariant.objects.get_or_create(
                media=media,
                variant_type='thumbnail',
                defaults={'size_bytes': 0}  # temporary, will be overwritten
            )

            if not created and variant.file:
                variant.file.delete(save=False)

            # Save the thumbnail file
            variant.file.save(variant_name, thumbnail_file)

            # Optionally get thumbnail dimensions (using PIL)
            try:
                with Image.open(variant.file) as thumb_img:
                    variant.width, variant.height = thumb_img.size
            except Exception:
                # If PIL can't read it, leave dimensions as None
                pass

            variant.size_bytes = variant.file.size
            variant.save()

            # Update metadata reference
            media.metadata['variants']['thumbnail'] = {
                'file': variant.file.name,
                'width': variant.width,
                'height': variant.height,
                'size_bytes': variant.size_bytes,
            }

            media.save(update_fields=['metadata'])
            logger.info(f"Processed video media {media.id}")

            # Clean up temporary file from extract_thumbnail
            os.unlink(tmp_path)

        except Exception as e:
            logger.exception(f"Failed to process video media {media.id}: {e}")

    @staticmethod
    def process_media(media: Media):
        """Detect media type and process accordingly."""
        ext = os.path.splitext(media.file.name)[1].lower()
        if ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'):
            return MediaProcessingService.process_image(media)
        elif ext in ('.mp4', '.mov', '.avi', '.webm', '.mkv'):
            return MediaProcessingService.process_video(media)
        else:
            logger.warning(f"Unsupported media type for media {media.id}: {media.file.name}")
            
            
            




def trigger_media_processing(media):
    """
    Process media asynchronously using Celery if available, otherwise threading.
    """
    # Check if we should use Celery (configurable in settings)
    use_celery = getattr(settings, 'MEDIA_PROCESSING_USE_CELERY', True)

    if use_celery:
        try:
            from feed.tasks.media import process_media_task
            process_media_task.delay(media.id)
            logger.debug(f"Scheduled media processing via Celery for media {media.id}")
            return
        except (ImportError, AttributeError, Exception) as e:
            logger.warning(f"Celery not available or task not defined: {e}, falling back to threading")

    # Fallback to threading

    threading.Thread(target=MediaProcessingService.process_media, args=(media,)).start()
    logger.debug(f"Scheduled media processing via threading for media {media.id}")