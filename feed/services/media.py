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
from django.forms import ValidationError
from feed.models import Media
from feed.models.media import MediaVariant
from django.db import transaction

logger = logging.getLogger(__name__)


class MediaProcessingService:
    """Handle processing of media files: generate variants, extract metadata."""

    @staticmethod
    def create(
        content_type: str = None,
        object_id: int = None,
        file=None,
        order=0,
        created_by=None,
    ):
        """Create a new media instance."""

        if not content_type:
            raise ValidationError("content_type is required to create media.")
        if not object_id:
            raise ValidationError("object_id is required to create media.")
        if not file:
            raise ValidationError("file is required to create media.")

        media_obj = Media.objects.create(
            created_by=created_by,
            content_type=content_type,
            object_id=object_id,
            file=file,
            order=order,
        )
        transaction.on_commit(
            lambda: trigger_media_processing(media_obj)  # gamitin ang function
        )

    @staticmethod
    def process_image(media: Media):
        """Generate thumbnails and resized versions for an image."""
        try:
            with media.file.open("rb") as f:
                with Image.open(f) as img:
                    # Original metadata (store in media.metadata)
                    width, height = img.size
                    img_format = img.format
                    media.metadata = {
                        "original": {
                            "width": width,
                            "height": height,
                            "format": img_format,
                            "size_bytes": media.file.size,
                        },
                        "variants": {},  # will be filled with variant references
                    }

                    # Define sizes and variant types
                    sizes = {
                        "thumbnail": (150, 150),
                        "small": (480, 480),
                        "medium": (1024, 1024),
                    }

                    # Base filename without extension, used for variant naming
                    base_filename = os.path.splitext(os.path.basename(media.file.name))[
                        0
                    ]
                    ext = os.path.splitext(media.file.name)[1].lower()

                    for variant_type, (max_width, max_height) in sizes.items():
                        # Create resized copy
                        img_copy = img.copy()
                        img_copy.thumbnail(
                            (max_width, max_height), Image.Resampling.LANCZOS
                        )

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
                                "width": img_copy.width,
                                "height": img_copy.height,
                                "size_bytes": len(content_file),
                            },
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
                        media.metadata["variants"][variant_type] = {
                            "file": variant.file.name,
                            "width": variant.width,
                            "height": variant.height,
                            "size_bytes": variant.size_bytes,
                        }

                    media.save(update_fields=["metadata"])
                    logger.info(f"Processed image media {media.id}")

        except Exception as e:
            logger.exception(f"Failed to process image media {media.id}: {e}")

    @staticmethod
    def process_video(media: Media):
        """Extract thumbnail, generate video variants, and store metadata."""
        try:
            from feed.utils.media import extract_thumbnail
            import subprocess
            import os
            import json
            from django.conf import settings

            # 1. Extract thumbnail
            thumbnail_file, tmp_thumb_path = extract_thumbnail(
                media.file, time="00:00:01"
            )
            base_filename = os.path.splitext(os.path.basename(media.file.name))[0]
            variant_name_thumb = f"{base_filename}_thumbnail.jpg"

            # Get or create thumbnail variant
            thumb_variant, created = MediaVariant.objects.get_or_create(
                media=media,
                variant_type="thumbnail",
                defaults={"size_bytes": 0},
            )
            if not created and thumb_variant.file:
                thumb_variant.file.delete(save=False)
            thumb_variant.file.save(variant_name_thumb, thumbnail_file)
            try:
                with Image.open(thumb_variant.file) as thumb_img:
                    thumb_variant.width, thumb_variant.height = thumb_img.size
            except:
                pass
            thumb_variant.size_bytes = thumb_variant.file.size
            thumb_variant.save()
            # Clean up temporary thumbnail
            os.unlink(tmp_thumb_path)

            # 2. Get original video metadata via ffprobe
            cmd_probe = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=width,height,duration,codec_name",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                media.file.path,
            ]
            result = subprocess.run(
                cmd_probe, capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)
            video_stream = next(
                (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
                {},
            )
            original_width = video_stream.get("width")
            original_height = video_stream.get("height")
            original_duration = float(
                video_stream.get("duration")
                or data.get("format", {}).get("duration", 0)
            )
            original_codec = video_stream.get("codec_name")

            # Store original metadata
            media.metadata = {
                "original": {
                    "width": original_width,
                    "height": original_height,
                    "duration": original_duration,
                    "codec": original_codec,
                    "size_bytes": media.file.size,
                },
                "variants": {},
            }

            # 3. Generate video variants (if configured)
            variants_config = getattr(settings, "VIDEO_VARIANTS", [])
            for config in variants_config:
                variant_type = config["type"]
                target_width = config["width"]
                target_height = config["height"]
                bitrate = config.get("bitrate", "1000k")

                # Build ffmpeg command to transcode
                output_filename = f"{base_filename}_{variant_type}.mp4"
                # We'll use a temporary file first to avoid partial writes
                import tempfile

                with tempfile.NamedTemporaryFile(
                    suffix=".mp4", delete=False
                ) as tmp_out:
                    tmp_output = tmp_out.name

                cmd = [
                    "ffmpeg",
                    "-i",
                    media.file.path,
                    "-vf",
                    f"scale={target_width}:{target_height}",
                    "-c:v",
                    "libx264",
                    "-b:v",
                    bitrate,
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-preset",
                    "medium",
                    "-movflags",
                    "+faststart",
                    tmp_output,
                    "-y",
                ]
                subprocess.run(cmd, check=True, capture_output=True)

                # Now create variant record and move file to final storage
                variant, created = MediaVariant.objects.get_or_create(
                    media=media,
                    variant_type=variant_type,
                    defaults={"size_bytes": 0},
                )
                if not created and variant.file:
                    variant.file.delete(save=False)

                with open(tmp_output, "rb") as f:
                    content_file = ContentFile(f.read())
                    variant.file.save(output_filename, content_file)

                # Get variant dimensions and size
                variant.width = target_width
                variant.height = target_height
                variant.size_bytes = variant.file.size
                variant.duration = original_duration  # same as original
                variant.codec = "h264"  # or read from ffprobe
                variant.save()

                # Store reference in media.metadata for backward compatibility
                media.metadata["variants"][variant_type] = {
                    "file": variant.file.name,
                    "width": target_width,
                    "height": target_height,
                    "size_bytes": variant.size_bytes,
                    "duration": original_duration,
                    "codec": variant.codec,
                }

                # Clean up temp file
                os.unlink(tmp_output)

            # Save updated media metadata
            media.save(update_fields=["metadata"])
            logger.info(
                f"Processed video media {media.id} with {len(variants_config)} variants"
            )

        except Exception as e:
            logger.exception(f"Failed to process video media {media.id}: {e}")
            # Optionally re-raise or log; we'll just log here

    @staticmethod
    def process_media(media: Media):
        """Detect media type and process accordingly."""
        ext = os.path.splitext(media.file.name)[1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
            return MediaProcessingService.process_image(media)
        elif ext in (".mp4", ".mov", ".avi", ".webm", ".mkv"):
            return MediaProcessingService.process_video(media)
        else:
            logger.warning(
                f"Unsupported media type for media {media.id}: {media.file.name}"
            )


def trigger_media_processing(media):
    """
    Process media asynchronously using Celery if available, otherwise threading.
    """
    # Check if we should use Celery (configurable in settings)
    use_celery = getattr(settings, "MEDIA_PROCESSING_USE_CELERY", True)

    if use_celery:
        try:
            from feed.tasks.media import process_media_task

            process_media_task.delay(media.id)
            logger.debug(f"Scheduled media processing via Celery for media {media.id}")
            return
        except (ImportError, AttributeError, Exception) as e:
            logger.warning(
                f"Celery not available or task not defined: {e}, falling back to threading"
            )

    # Fallback to threading

    threading.Thread(target=MediaProcessingService.process_media, args=(media,)).start()
    logger.debug(f"Scheduled media processing via threading for media {media.id}")
