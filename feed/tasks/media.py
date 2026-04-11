from events.models import Event
from django.contrib.contenttypes.models import ContentType
from feed.models import Reel, Media
from feed.models.post import Post
from celery import shared_task
from django.core.files import File
import os

@shared_task
def process_media_task(media_id: int) -> None:
    from feed.services.media import MediaProcessingService
    from feed.models import Media

    try:
        media = Media.objects.get(id=media_id)
        MediaProcessingService.process_media(media)
    except Media.DoesNotExist:
        pass


@shared_task
def finalize_reel_upload(reel_id, temp_path):
    from feed.services.media import MediaProcessingService
    try:
        reel = Reel.objects.get(id=reel_id)
        with open(temp_path, "rb") as f:
            django_file = File(f, name=os.path.basename(temp_path))
            reel_ct = ContentType.objects.get_for_model(reel)
            media = Media.objects.create(
                content_type=reel_ct,
                object_id=reel.id,
                file=django_file,
                order=0,
                created_by=reel.user,
            )
            # Optionally trigger further processing (thumbnails, variants)
            MediaProcessingService.process_media(media)

        reel.processing = False
        reel.temp_file_path = ""
        reel.save(update_fields=["processing", "temp_file_path"])
    except Exception as e:
        # Mark as failed so it doesn't stay processing forever
        reel = Reel.objects.get(id=reel_id)
        reel.processing = False
        reel.temp_file_path = ""
        reel.save(update_fields=["processing", "temp_file_path"])
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@shared_task
def finalize_post_upload(post_id, temp_paths):
    from feed.services.media import MediaProcessingService
    try:
        post = Post.objects.get(id=post_id)
        post_ct = ContentType.objects.get_for_model(post)
        media_objects = []
        for order, temp_path in enumerate(temp_paths):
            with open(temp_path, "rb") as f:
                django_file = File(f, name=os.path.basename(temp_path))
                media = Media.objects.create(
                    content_type=post_ct,
                    object_id=post.id,
                    file=django_file,
                    order=order,
                    created_by=post.user,
                )
                media_objects.append(media)
            # Clean up temp file
            os.remove(temp_path)

        # Optionally process each media (thumbnails, etc.)
        for media in media_objects:
            MediaProcessingService.process_media(media)

        post.processing = False
        post.temp_file_paths = []
        post.save(update_fields=["processing", "temp_file_paths"])
    except Exception as e:
        # Mark as failed and clean up
        try:
            post = Post.objects.get(id=post_id)
            post.processing = False
            post.temp_file_paths = []
            post.save(update_fields=["processing", "temp_file_paths"])
        except:
            pass
        # Delete any leftover temp files
        for path in temp_paths:
            if os.path.exists(path):
                os.remove(path)
        raise


@shared_task
def finalize_event_upload(event_id, temp_paths):
    from feed.services.media import MediaProcessingService
    try:
        event = Event.objects.get(id=event_id)
        event_ct = ContentType.objects.get_for_model(event)
        media_objects = []
        for order, temp_path in enumerate(temp_paths):
            with open(temp_path, "rb") as f:
                django_file = File(f, name=os.path.basename(temp_path))
                media = Media.objects.create(
                    content_type=event_ct,
                    object_id=event.id,
                    file=django_file,
                    order=order,
                    created_by=event.organizer,
                )
                media_objects.append(media)
            os.remove(temp_path)

        # Process media (thumbnails, variants)
        for media in media_objects:
            MediaProcessingService.process_media(media)

        event.processing = False
        event.temp_file_paths = []
        event.save(update_fields=["processing", "temp_file_paths"])
    except Exception:
        # Mark as failed
        event = Event.objects.get(id=event_id)
        event.processing = False
        event.temp_file_paths = []
        event.save(update_fields=["processing", "temp_file_paths"])
        # Clean up leftover temp files
        for path in temp_paths:
            if os.path.exists(path):
                os.remove(path)
        raise
