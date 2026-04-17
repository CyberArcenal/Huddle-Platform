import os
import tempfile
import subprocess
import logging
from django.core.files import File
from django.core.files.base import ContentFile   # ← idagdag mo ito

logger = logging.getLogger(__name__)

def extract_thumbnail(file_or_path, output_format='jpg', time='00:00:01'):
    """
    Extract thumbnail using ffmpeg - FIXED version (walang closed file issue)
    """
    video_tmp_path = None

    # 1. Normalize input to local path
    if isinstance(file_or_path, str):
        video_path = file_or_path
    else:
        video_path = getattr(file_or_path, "path", None)
        if not video_path or not os.path.exists(video_path):
            suffix = os.path.splitext(getattr(file_or_path, "name", "video"))[1] or ".mp4"
            tmp_video = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            video_tmp_path = tmp_video.name

            try:
                file_or_path.seek(0)
            except Exception:
                pass

            with open(video_tmp_path, "wb") as out_f:
                chunk = file_or_path.read(8192)
                while chunk:
                    out_f.write(chunk)
                    chunk = file_or_path.read(8192)

            logger.info(f"[extract_thumbnail] Copied video to temp: {video_tmp_path}")

    if not os.path.exists(video_path):
        raise Exception(f"Video path does not exist: {video_path}")

    # 2. Thumbnail temp file
    thumb_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{output_format}")
    thumbnail_path = thumb_tmp.name
    thumb_tmp.close()

    # 3. Better ffmpeg command
    cmd = [
        "ffmpeg",
        "-ss", time,
        "-i", video_path,
        "-vframes", "1",
        "-vf", "scale=640:-2",      # 640px wide, good quality
        "-q:v", "2",                # high quality
        "-y",
        thumbnail_path
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        size = os.path.getsize(thumbnail_path)
        logger.info(f"[extract_thumbnail] SUCCESS → {size} bytes thumbnail generated")

        # FIXED: Gamitin ang ContentFile para hindi magkaroon ng closed file issue
        with open(thumbnail_path, "rb") as f:
            content = f.read()

        django_thumb = ContentFile(content, name=os.path.basename(thumbnail_path))

        return django_thumb, thumbnail_path, video_tmp_path

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if hasattr(e, "stderr") else str(e)
        logger.error(f"[extract_thumbnail] ffmpeg failed: {stderr}")

        # cleanup
        if os.path.exists(thumbnail_path):
            os.unlink(thumbnail_path)
        if video_tmp_path and os.path.exists(video_tmp_path):
            os.unlink(video_tmp_path)

        raise Exception(f"Failed to extract thumbnail: {stderr}")