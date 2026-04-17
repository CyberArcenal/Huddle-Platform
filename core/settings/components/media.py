

# Settings for video transcoding variants (width, height, bitrate)
VIDEO_VARIANTS = [
    {"type": "video_480p", "width": 854, "height": 480, "bitrate": "1000k"},
    {"type": "video_720p", "width": 1280, "height": 720, "bitrate": "2000k"},
    # {"type": "video_1080p", "width": 1920, "height": 1080, "bitrate": "4000k"},
]

MAX_IMAGE_SIZE = 10 * 1024 * 1024      # 10 MB
MAX_VIDEO_SIZE = 1000 * 1024 * 1024      # 1GB MB
MAX_AUDIO_SIZE = 20 * 1024 * 1024      # 20 MB
MAX_THUMBNAIL_SIZE = 5 * 1024 * 1024   # 5 MB
MAX_MEDIA_SIZE = 20 * 1024 * 1024      # 20 MB (for general media uploads)
MAX_REEL_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB (reels have a higher limit)


STORY_VIDEO_MAX_SIZE = 60 * 1024 * 1024 # 60 mb
STORY_IMAGE_MAX_SIZE = 10 * 1024 * 1024 # 10 mb

USER_IMAGE_MAX_SIZE = 8 * 1024 * 1024 # 8 mb



# Image compression settings
MAX_IMAGE_DIMENSION = 2048          # maximum width or height
IMAGE_COMPRESSION_QUALITY = 85      # 1-100, lower = smaller file

THUMBNAIL_SIZE = 320                      # width and height for thumbnail variants
SMALL_IMAGE_SIZE = 480                   # width and height for small image variants
MEDIUM_IMAGE_SIZE = 720                  # width and height for medium image variants


# Video compression settings
VIDEO_COMPRESSION_CRF = 28          # higher = smaller file (18-28 recommended)
VIDEO_COMPRESSION_MAX_WIDTH = 1280  # downscale if original width exceeds this
VIDEO_COMPRESSION_BITRATE = None    # if set, overrides CRF (e.g., '2M')


ANIMATED_THUMBNAIL_DURATION = 3
ANIMATED_THUMBNAIL_WIDTH = 320


# User image compression settings
USER_IMAGE_MAX_DIMENSION = 720   # maximum width or height after compression
USER_IMAGE_COMPRESSION_QUALITY = 75  # 1-100, lower = smaller file


# Story media compression
STORY_IMAGE_QUALITY = 75          # 1-100, lower = smaller
STORY_VIDEO_CRF = 28              # 18-28, higher = smaller
STORY_MEDIA_USE_CELERY = False    # set True kung may Celery