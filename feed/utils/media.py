import os
import tempfile
import subprocess
from django.core.files import File

def extract_thumbnail(file_or_path, output_format='jpg', time='00:00:01'):
    """
    Extract a thumbnail using ffmpeg.
    Returns: (django.core.files.File thumbnail_file, thumbnail_tmp_path, video_tmp_path)
      - thumbnail_tmp_path: path to the generated thumbnail temp file (caller should delete)
      - video_tmp_path: path to a temp copy of the video if one was created, else None
    Accepts:
      - a filesystem path string, or
      - a Django FieldFile / file-like object (will be copied to a temp file if needed)
    """
    video_tmp_path = None

    # Normalize input to a local filesystem path
    if isinstance(file_or_path, str):
        video_path = file_or_path
    else:
        # file_or_path is a FieldFile or file-like
        video_path = getattr(file_or_path, "path", None)
        if not video_path or not os.path.exists(video_path):
            # copy to temp file
            suffix = os.path.splitext(getattr(file_or_path, "name", "video"))[1] or ".mp4"
            tmp_video = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            try:
                file_or_path.seek(0)
            except Exception:
                pass
            # read in chunks to avoid memory spikes
            with open(tmp_video.name, "wb") as out_f:
                chunk = file_or_path.read(8192)
                while chunk:
                    out_f.write(chunk)
                    chunk = file_or_path.read(8192)
            video_tmp_path = tmp_video.name
            video_path = video_tmp_path

    if not os.path.exists(video_path):
        raise Exception(f"Video path does not exist: {video_path}")

    # Create thumbnail temp file
    thumb_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{output_format}")
    thumbnail_path = thumb_tmp.name
    thumb_tmp.close()

    cmd = [
        "ffmpeg", "-i", video_path,
        "-ss", time,
        "-vframes", "1",
        "-f", "image2",
        thumbnail_path
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        # Open the generated thumbnail as a Django File (caller will delete thumbnail_path)
        f = open(thumbnail_path, "rb")
        django_thumb = File(f, name=os.path.basename(thumbnail_path))
        return django_thumb, thumbnail_path, video_tmp_path
    except subprocess.CalledProcessError as e:
        # cleanup on failure
        if os.path.exists(thumbnail_path):
            try:
                os.unlink(thumbnail_path)
            except Exception:
                pass
        if video_tmp_path and os.path.exists(video_tmp_path):
            try:
                os.unlink(video_tmp_path)
            except Exception:
                pass
        stderr = e.stderr if hasattr(e, "stderr") else str(e)
        raise Exception(f"Failed to extract thumbnail: {stderr}")
