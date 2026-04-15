import json
import os
import logging
from io import BytesIO
import subprocess
import threading
import tempfile
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
    """Handle processing of media files: generate variants, extract metadata, then compress original."""

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
            lambda: trigger_media_processing(media_obj)
        )

    @staticmethod
    def process_image(media: Media):
        """Generate thumbnails and resized versions for an image, then compress original."""
        try:
            with media.file.open("rb") as f:
                with Image.open(f) as img:
                    # Original metadata (store in media.metadata)
                    width, height = img.size
                    img_format = img.format
                    original_size = media.file.size
                    media.metadata = {
                        "original": {
                            "width": width,
                            "height": height,
                            "format": img_format,
                            "size_bytes": original_size,
                        },
                        "variants": {},  # will be filled with variant references
                    }

                    # Define sizes and variant types
                    sizes = {
                        "thumbnail": (150, 150),
                        "small": (480, 480),
                        "medium": (720, 720),
                    }

                    # Base filename without extension, used for variant naming
                    base_filename = os.path.splitext(os.path.basename(media.file.name))[0]
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

                        # Store reference in media.metadata
                        media.metadata["variants"][variant_type] = {
                            "file": variant.file.name,
                            "width": variant.width,
                            "height": variant.height,
                            "size_bytes": variant.size_bytes,
                        }

                    # ===== COMPRESS ORIGINAL IMAGE =====
                    max_dim = getattr(settings, "MAX_IMAGE_DIMENSION", 1080)
                    quality = getattr(settings, "IMAGE_COMPRESSION_QUALITY", 80)

                    compressed_img = img.copy()
                    if max(compressed_img.size) > max_dim:
                        compressed_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                    buffer = BytesIO()
                    save_format = img_format if img_format in ['JPEG', 'PNG', 'WEBP'] else 'JPEG'
                    if save_format == 'JPEG':
                        compressed_img.save(buffer, format=save_format, quality=quality, optimize=True)
                    else:
                        compressed_img.save(buffer, format=save_format, optimize=True)
                    buffer.seek(0)

                    # Replace original file
                    original_name = media.file.name
                    media.file.delete(save=False)  # delete old file
                    new_file = ContentFile(buffer.read())
                    media.file.save(original_name, new_file, save=False)

                    # Update metadata for original (now compressed)
                    media.metadata["original"] = {
                        "width": compressed_img.width,
                        "height": compressed_img.height,
                        "format": save_format,
                        "size_bytes": media.file.size,
                        "compressed": True,
                        "original_size_bytes": original_size,
                    }
                    media.save(update_fields=["file", "metadata"])
                    logger.info(f"Processed and compressed image media {media.id}")

        except Exception as e:
            logger.exception(f"Failed to process image media {media.id}: {e}")

    @staticmethod
    def process_video(media: Media):
        """Extract thumbnail, generate video variants, and compress original."""
        try:
            from feed.utils.media import extract_thumbnail

            # 1. Extract static thumbnail
            thumbnail_file, tmp_thumb_path, video_tmp_path = extract_thumbnail(
                media.file, time="00:00:01"
            )
            base_filename = os.path.splitext(os.path.basename(media.file.name))[0]
            variant_name_thumb = f"{base_filename}_thumbnail.jpg"

            thumb_variant, created = MediaVariant.objects.get_or_create(
                media=media,
                variant_type="thumbnail",
                defaults={"size_bytes": 0},
            )
            if not created and thumb_variant.file:
                thumb_variant.file.delete(save=False)
            thumb_variant.file.save(variant_name_thumb, thumbnail_file)
            thumbnail_file.close()

            try:
                with Image.open(thumb_variant.file) as thumb_img:
                    thumb_variant.width, thumb_variant.height = thumb_img.size
            except:
                pass
            thumb_variant.size_bytes = thumb_variant.file.size
            thumb_variant.save()

            os.unlink(tmp_thumb_path)
            if video_tmp_path and os.path.exists(video_tmp_path):
                os.unlink(video_tmp_path)

            # 2. Original video metadata
            cmd_probe = [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=width,height,duration,codec_name",
                "-show_entries", "format=duration",
                "-of", "json", media.file.path,
            ]
            result = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            video_stream = next(
                (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
                {},
            )
            original_width = video_stream.get("width")
            original_height = video_stream.get("height")
            original_duration = float(
                video_stream.get("duration") or data.get("format", {}).get("duration", 0)
            )
            original_codec = video_stream.get("codec_name")
            original_size = media.file.size

            media.metadata = {
                "original": {
                    "width": original_width,
                    "height": original_height,
                    "duration": original_duration,
                    "codec": original_codec,
                    "size_bytes": original_size,
                },
                "variants": {},
            }

            # ===== 3. Create 3-second video thumbnail (animated) =====
            animated_thumb_duration = getattr(settings, "ANIMATED_THUMBNAIL_DURATION", 3)
            animated_thumb_width = getattr(settings, "ANIMATED_THUMBNAIL_WIDTH", 320)

            if original_width and original_height:
                target_height = int(animated_thumb_width * original_height / original_width)
            else:
                target_height = animated_thumb_width

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_anim:
                tmp_anim_path = tmp_anim.name

            cmd_anim_thumb = [
                "ffmpeg",
                "-i", media.file.path,
                "-t", str(animated_thumb_duration),
                "-vf", f"scale={animated_thumb_width}:{target_height}",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "28",
                "-c:a", "aac",
                "-b:a", "64k",
                "-movflags", "+faststart",
                tmp_anim_path,
                "-y"
            ]
            subprocess.run(cmd_anim_thumb, check=True, capture_output=True)

            anim_variant, created = MediaVariant.objects.get_or_create(
                media=media,
                variant_type="video_thumbnail",
                defaults={"size_bytes": 0}
            )
            if not created and anim_variant.file:
                anim_variant.file.delete(save=False)

            anim_filename = f"{base_filename}_anim_thumb.mp4"
            with open(tmp_anim_path, "rb") as f:
                content_file = ContentFile(f.read())
                anim_variant.file.save(anim_filename, content_file)

            anim_variant.width = animated_thumb_width
            anim_variant.height = target_height
            anim_variant.size_bytes = anim_variant.file.size
            anim_variant.duration = animated_thumb_duration
            anim_variant.codec = "h264"
            anim_variant.save()

            media.metadata["variants"]["video_thumbnail"] = {
                "file": anim_variant.file.name,
                "width": animated_thumb_width,
                "height": target_height,
                "size_bytes": anim_variant.size_bytes,
                "duration": animated_thumb_duration,
                "codec": "h264",
            }

            os.unlink(tmp_anim_path)

            # ===== 4. Generate other video variants (480p, 720p, etc.) =====
            variants_config = getattr(settings, "VIDEO_VARIANTS", [])
            for config in variants_config:
                variant_type = config["type"]
                target_width = config["width"]
                target_height = config["height"]
                bitrate = config.get("bitrate", "1000k")

                output_filename = f"{base_filename}_{variant_type}.mp4"
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_out:
                    tmp_output = tmp_out.name

                cmd = [
                    "ffmpeg",
                    "-i", media.file.path,
                    "-vf", f"scale={target_width}:{target_height}",
                    "-c:v", "libx264",
                    "-b:v", bitrate,
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-preset", "medium",
                    "-movflags", "+faststart",
                    tmp_output,
                    "-y",
                ]
                subprocess.run(cmd, check=True, capture_output=True)

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

                variant.width = target_width
                variant.height = target_height
                variant.size_bytes = variant.file.size
                variant.duration = original_duration
                variant.codec = "h264"
                variant.save()

                media.metadata["variants"][variant_type] = {
                    "file": variant.file.name,
                    "width": target_width,
                    "height": target_height,
                    "size_bytes": variant.size_bytes,
                    "duration": original_duration,
                    "codec": variant.codec,
                }

                os.unlink(tmp_output)

            # ===== 5. COMPRESS ORIGINAL VIDEO =====
            crf = getattr(settings, "VIDEO_COMPRESSION_CRF", 28)
            max_width = getattr(settings, "VIDEO_COMPRESSION_MAX_WIDTH", 1280)
            bitrate = getattr(settings, "VIDEO_COMPRESSION_BITRATE", None)

            scale_filter = ""
            if original_width and original_width > max_width:
                scale_filter = f"scale={max_width}:-2"
            else:
                scale_filter = "scale=iw:ih"

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_compressed:
                compressed_path = tmp_compressed.name

            cmd_compress = [
                "ffmpeg",
                "-i", media.file.path,
                "-vf", scale_filter,
                "-c:v", "libx264",
            ]
            if bitrate:
                cmd_compress.extend(["-b:v", bitrate])
            else:
                cmd_compress.extend(["-crf", str(crf)])
            cmd_compress.extend([
                "-preset", "medium",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                compressed_path,
                "-y"
            ])
            subprocess.run(cmd_compress, check=True, capture_output=True)

            # Get new dimensions if scaled
            if scale_filter != "scale=iw:ih":
                probe_cmd = [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "default=noprint_wrappers=1",
                    compressed_path
                ]
                result_probe = subprocess.run(probe_cmd, capture_output=True, text=True)
                lines = result_probe.stdout.strip().split()
                new_width = int(lines[0].split('=')[1]) if lines else original_width
                new_height = int(lines[1].split('=')[1]) if len(lines) > 1 else original_height
            else:
                new_width = original_width
                new_height = original_height

            # Replace original file
            original_name = media.file.name
            media.file.delete(save=False)
            with open(compressed_path, "rb") as f:
                new_content = ContentFile(f.read())
                media.file.save(original_name, new_content, save=False)

            # Update metadata
            media.metadata["original"] = {
                "width": new_width,
                "height": new_height,
                "duration": original_duration,
                "codec": "h264",
                "size_bytes": media.file.size,
                "compressed": True,
                "original_size_bytes": original_size,
            }
            media.save(update_fields=["file", "metadata"])

            os.unlink(compressed_path)
            logger.info(f"Processed and compressed video media {media.id}")

        except Exception as e:
            logger.exception(f"Failed to process video media {media.id}: {e}")

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

    threading.Thread(target=MediaProcessingService.process_media, args=(media,)).start()
    logger.debug(f"Scheduled media processing via threading for media {media.id}")