import subprocess
import os
import tempfile
from django.core.files import File

def extract_thumbnail(video_file, output_format='jpg', time='00:00:01'):
    """
    Extract a thumbnail from a video file using ffmpeg.
    Returns a tuple: (Django File object, path to temporary file).
    The caller should clean up the temporary file after use.
    """
    with tempfile.NamedTemporaryFile(suffix=f'.{output_format}', delete=False) as tmp:
        thumbnail_path = tmp.name

    cmd = [
        'ffmpeg', '-i', video_file.name,
        '-ss', time,
        '-vframes', '1',
        '-f', 'image2',
        thumbnail_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        with open(thumbnail_path, 'rb') as f:
            thumbnail_file = File(f, name=os.path.basename(thumbnail_path))
        return thumbnail_file, thumbnail_path
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to extract thumbnail: {e.stderr}")