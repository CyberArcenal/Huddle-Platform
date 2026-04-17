import logging
import traceback

from events.models import Event
from django.contrib.contenttypes.models import ContentType
from feed.models import Reel, Media
from feed.models.post import Post
from celery import shared_task
from django.core.files import File
import os



logger = logging.getLogger(__name__)

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
    logger.info(f"Finalizing reel upload for reel_id={reel_id} with temp_path={temp_path}")
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
            
            thumbnail_variant = media.variants.filter(variant_type='thumbnail').first()
            if thumbnail_variant:
                reel.thumbnail_variant = thumbnail_variant
                reel.save(update_fields=['thumbnail_variant'])
            
        reel.processing = False
        reel.temp_file_path = ""
        reel.save(update_fields=["processing", "temp_file_path"])
    except Exception as e:
        logger.exception(f"Error finalizing reel {reel_id}: {e}")
        # Mark as failed so it doesn't stay processing forever
        reel = Reel.objects.get(id=reel_id)
        reel.processing = False
        reel.temp_file_path = ""
        reel.save(update_fields=["processing", "temp_file_path"])
        traceback.print_exc()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)



@shared_task
def finalize_post_upload(post_id, temp_paths):
    from feed.services.media import MediaProcessingService
    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        # Post was deleted before the task could process it.
        # Clean up temp files and return.
        for path in temp_paths:
            if os.path.exists(path):
                os.remove(path)
        logger.warning(f"Post {post_id} not found during finalize_post_upload. Cleaning temp files.")
        return

    try:
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
            os.remove(temp_path)

        for media in media_objects:
            MediaProcessingService.process_media(media)

        post.processing = False
        post.temp_file_paths = []
        post.save(update_fields=["processing", "temp_file_paths"])
    except Exception as e:
        logger.exception(f"Error finalizing post {post_id}: {e}")
        # Ensure processing flag is cleared even on other errors
        try:
            post = Post.objects.get(id=post_id)
            post.processing = False
            post.temp_file_paths = []
            post.save(update_fields=["processing", "temp_file_paths"])
        except Post.DoesNotExist:
            pass
        # Clean up any leftover temp files
        for path in temp_paths:
            if os.path.exists(path):
                os.remove(path)
        raise





@shared_task(name='feed.tasks.media.regenerate_broken_media_variants')
def regenerate_broken_media_variants(
    limit=30,
    force=False,
    only_reels=False,
    only_posts=False,
    media_ids=None
):
    """
    Celery task na magre-regenerate ng broken thumbnails at variants.
    """
    from feed.services.media import MediaProcessingService
    if media_ids:
        queryset = Media.objects.filter(id__in=media_ids)
    else:
        queryset = Media.objects.select_related('content_type').all()

        if only_reels:
            reel_ct = ContentType.objects.get_for_model(Reel)
            queryset = queryset.filter(content_type=reel_ct)
        elif only_posts:
            post_ct = ContentType.objects.get_for_model(Post)
            queryset = queryset.filter(content_type=post_ct)

    queryset = queryset[:limit]

    logger.info(f"🔄 Starting broken variants regeneration | "
                f"force={force}, limit={limit}, reels_only={only_reels}, total_found={queryset.count()}")

    fixed = 0
    for media in queryset:
        try:
            # Check kung may broken variant
            has_broken = any(
                MediaProcessingService.is_variant_broken(v) 
                for v in media.variants.all()
            ) or media.variants.count() == 0

            if force or has_broken:
                MediaProcessingService.regenerate_variants(media, force=force)
                fixed += 1
        except Exception as e:
            logger.error(f"Failed to regenerate media {media.id}: {e}")

    logger.info(f"✅ Regeneration task completed! Fixed {fixed} media items.")
    return f"Successfully processed {fixed} media items."