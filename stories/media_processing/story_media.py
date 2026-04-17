# stories/services/story_media.py
import os
import logging
from io import BytesIO
import threading
import subprocess
import tempfile
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from stories.models import Story

logger = logging.getLogger(__name__)


class StoryMediaProcessingService:
    """Compress story media to 720p and generate thumbnail."""

    @staticmethod
    def process_story_media(story: Story):
        if story.story_type == 'image':
            StoryMediaProcessingService._process_image(story)
        elif story.story_type == 'video':
            StoryMediaProcessingService._process_video(story)

    @staticmethod
    def _process_image(story: Story):
        """Compress image to 720p, create thumbnail, replace original."""
        try:
            with story.media_url.open("rb") as f:
                with Image.open(f) as img:
                    MAX_DIM = 720
                    QUALITY = 75
                    THUMB_SIZE = (320, 320)

                    # Create thumbnail first (from original)
                    thumb_img = img.copy()
                    thumb_img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                    thumb_buffer = BytesIO()
                    thumb_img.save(thumb_buffer, format='JPEG', quality=70, optimize=True)
                    thumb_buffer.seek(0)
                    thumb_name = f"{os.path.splitext(story.media_url.name)[0]}_thumb.jpg"
                    story.thumbnail.save(thumb_name, ContentFile(thumb_buffer.read()), save=False)

                    # Compress original image
                    compressed = img.copy()
                    if max(compressed.size) > MAX_DIM:
                        compressed.thumbnail((MAX_DIM, MAX_DIM), Image.Resampling.LANCZOS)

                    buffer = BytesIO()
                    compressed.save(buffer, format='JPEG', quality=QUALITY, optimize=True)
                    buffer.seek(0)

                    # Replace original file
                    original_name = story.media_url.name
                    story.media_url.delete(save=False)
                    new_name = os.path.splitext(original_name)[0] + '.jpg'
                    story.media_url.save(new_name, ContentFile(buffer.read()), save=False)

                    story.save(update_fields=['media_url', 'thumbnail'])
                    logger.info(f"Processed story image {story.id}: compressed + thumbnail created")

        except Exception as e:
            logger.exception(f"Failed to process story image {story.id}: {e}")

    @staticmethod
    def _process_video(story: Story):
        """Compress video to 720p and extract thumbnail frame."""
        try:
            # Get original width
            cmd_probe = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width",
                "-of", "default=noprint_wrappers=1:nokey=1",
                story.media_url.path
            ]
            result = subprocess.run(cmd_probe, capture_output=True, text=True)
            orig_width = int(result.stdout.strip()) if result.stdout.strip() else None

            TARGET_WIDTH = 720
            CRF = 28

            # Extract thumbnail (first frame, resize to 320px width)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_thumb:
                thumb_path = tmp_thumb.name
            cmd_thumb = [
                "ffmpeg", "-i", story.media_url.path,
                "-ss", "00:00:01", "-vframes", "1",
                "-vf", "scale=320:-2",  # thumbnail width 320px, height auto
                thumb_path, "-y"
            ]
            subprocess.run(cmd_thumb, check=True, capture_output=True)

            # Save thumbnail to model
            thumb_name = f"{os.path.splitext(story.media_url.name)[0]}_thumb.jpg"
            with open(thumb_path, "rb") as f:
                story.thumbnail.save(thumb_name, ContentFile(f.read()), save=False)
            os.unlink(thumb_path)

            # Compress video
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
                compressed_path = tmp_video.name

            scale_filter = f"scale={TARGET_WIDTH}:-2" if (orig_width and orig_width > TARGET_WIDTH) else "scale=iw:ih"
            cmd_compress = [
                "ffmpeg", "-i", story.media_url.path,
                "-vf", scale_filter,
                "-c:v", "libx264", "-crf", str(CRF),
                "-preset", "fast",
                "-c:a", "aac", "-b:a", "96k",
                "-movflags", "+faststart",
                compressed_path, "-y"
            ]
            subprocess.run(cmd_compress, check=True, capture_output=True)

            # Replace original file
            original_name = story.media_url.name
            story.media_url.delete(save=False)
            with open(compressed_path, "rb") as f:
                story.media_url.save(original_name, ContentFile(f.read()), save=False)
            os.unlink(compressed_path)

            story.save(update_fields=['media_url', 'thumbnail'])
            logger.info(f"Processed story video {story.id}: compressed + thumbnail created")

        except Exception as e:
            logger.exception(f"Failed to process story video {story.id}: {e}")


def trigger_story_media_processing(story: Story):
    threading.Thread(target=StoryMediaProcessingService.process_story_media, args=(story,)).start()