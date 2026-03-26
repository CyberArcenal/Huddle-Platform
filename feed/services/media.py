import os
import logging
from io import BytesIO
import threading
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from feed.models import Media


logger = logging.getLogger(__name__)



    
    
    

class MediaProcessingService:
    """Handle processing of media files: generate variants, extract metadata."""

    @staticmethod
    def process_image(media: Media):
        """Generate thumbnails and resized versions for an image."""
        try:
            with Image.open(media.file) as img:
                # Original metadata
                width, height = img.size
                img_format = img.format
                metadata = {
                    'original': {
                        'width': width,
                        'height': height,
                        'format': img_format,
                        'size_bytes': media.file.size,
                    },
                    'variants': {},
                }

                # Define sizes: thumbnail (150x150), small (480x480), medium (1024x1024)
                sizes = {
                    'thumbnail': (150, 150),
                    'small': (480, 480),
                    'medium': (1024, 1024),
                }

                for name, (max_width, max_height) in sizes.items():
                    # Create a copy and resize maintaining aspect ratio
                    img_copy = img.copy()
                    img_copy.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                    # Save to buffer
                    buffer = BytesIO()
                    img_copy.save(buffer, format=img_format, quality=85)
                    buffer.seek(0)

                    # Generate filename for variant
                    base, ext = os.path.splitext(media.file.name)
                    variant_name = f"{base}_{name}{ext}"

                    # Save to storage
                    variant_path = default_storage.save(variant_name, ContentFile(buffer.read()))

                    metadata['variants'][name] = {
                        'file': variant_path,
                        'width': img_copy.width,
                        'height': img_copy.height,
                        'size_bytes': default_storage.size(variant_path),
                    }

                media.metadata = metadata
                media.save(update_fields=['metadata'])
                logger.info(f"Processed image media {media.id}")

        except Exception as e:
            logger.exception(f"Failed to process image media {media.id}: {e}")

    @staticmethod
    def process_video(media: Media):
        """Extract thumbnail for video."""
        try:
            # Reuse the extract_thumbnail helper from earlier
            from feed.utils.media import extract_thumbnail
            thumbnail_file, tmp_path = extract_thumbnail(media.file, time='00:00:01')

            # Save thumbnail to storage
            thumb_name = f"thumb_{media.file.name.replace('/', '_')}.jpg"
            saved_path = default_storage.save(thumb_name, thumbnail_file)

            # Optionally, use ffprobe to get video metadata
            import subprocess, json
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'stream=width,height,duration,codec_name',
                '-of', 'json',
                media.file.path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), {})

            metadata = {
                'original': {
                    'width': video_stream.get('width'),
                    'height': video_stream.get('height'),
                    'duration': float(video_stream.get('duration', 0)),
                    'codec': video_stream.get('codec_name'),
                },
                'variants': {
                    'thumbnail': {
                        'file': saved_path,
                        'width': None,   # can be updated if needed
                        'height': None,
                    }
                }
            }
            media.metadata = metadata
            media.save(update_fields=['metadata'])
            logger.info(f"Processed video media {media.id}")

            # Clean up temp file
            os.unlink(tmp_path)
        except Exception as e:
            logger.exception(f"Failed to process video media {media.id}: {e}")

    @staticmethod
    def process_media(media: Media):
        """Detect media type and process accordingly."""
        # Check by file extension
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