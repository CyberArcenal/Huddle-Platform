# feed/tasks/reel_cleanup.py
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.db.models import Q, F
from django.core.files.storage import default_storage

from feed.models import Reel, Media

logger = logging.getLogger(__name__)


@shared_task
def delete_corrupted_reels(
    minutes_stuck: int = 15,
    soft_delete: bool = True,
    dry_run: bool = False
) -> dict:
    """
    Identify and delete reels with corrupted video.

    Conditions for a reel to be considered corrupted:
    1. processing = True AND created_at < now - minutes_stuck (stuck processing)
    2. processing = False BUT:
        a. No associated Media object
        b. Media file is missing from storage
        c. Media has no video variant with valid duration (> 0)
        d. No thumbnail variant exists (indicates failed processing)

    Args:
        minutes_stuck: How long to wait before considering a processing reel as stuck/corrupted
        soft_delete: If True, set is_deleted=True. If False, hard delete the reel.
        dry_run: If True, only log and count, do not actually delete.

    Returns:
        dict with counts: {"deleted": int, "skipped": int, "total_checked": int}
    """
    threshold = timezone.now() - timedelta(minutes=minutes_stuck)
    corrupted_reels = []
    total_checked = 0

    # Query only non-deleted reels (if soft_delete, we will mark them)
    base_qs = Reel.objects.filter(is_deleted=False)

    # 1. Stuck processing reels
    stuck_processing = base_qs.filter(
        processing=True,
        created_at__lt=threshold
    )
    total_checked += stuck_processing.count()

    for reel in stuck_processing:
        logger.warning(f"Reel {reel.id} stuck in processing for > {minutes_stuck} minutes")
        corrupted_reels.append(reel)

    # 2. Finished processing reels that are corrupted
    finished_qs = base_qs.filter(processing=False)

    for reel in finished_qs:
        total_checked += 1
        if _is_reel_corrupted(reel):
            logger.warning(f"Reel {reel.id} has corrupted video")
            corrupted_reels.append(reel)

    deleted_count = 0
    if not dry_run:
        for reel in corrupted_reels:
            try:
                if soft_delete:
                    reel.is_deleted = True
                    reel.processing = False  # ensure it's not stuck
                    reel.save(update_fields=['is_deleted', 'processing'])
                else:
                    # Hard delete – also deletes related Media (cascade)
                    reel.delete()
                deleted_count += 1
            except Exception as e:
                logger.exception(f"Failed to delete reel {reel.id}: {e}")

    logger.info(
        f"Corrupted reels task completed: total_checked={total_checked}, "
        f"corrupted_found={len(corrupted_reels)}, deleted={deleted_count}, dry_run={dry_run}"
    )

    return {
        "deleted": deleted_count,
        "skipped": len(corrupted_reels) - deleted_count,
        "total_checked": total_checked,
    }


def _is_reel_corrupted(reel: Reel) -> bool:
    """Return True if the reel's main video is corrupted."""
    # Get all associated Media objects for this reel
    medias = reel.media.all()  # GenericRelation
    if not medias.exists():
        # No video file at all – definitely corrupted
        return True

    # Usually the first media (order=0) is the main video
    main_media = medias.first()

    # Check 1: Does the file exist on storage?
    if main_media.file and not default_storage.exists(main_media.file.name):
        logger.debug(f"Reel {reel.id}: media file missing from storage")
        return True

    # Check 2: Does it have any video variant with valid duration?
    video_variants = main_media.variants.filter(
        variant_type__in=['video_preview', 'video_transcoded', 'video_480p', 'video_720p', 'video_1080p']
    )
    has_valid_duration = video_variants.filter(duration__gt=0).exists()
    if not has_valid_duration:
        # Also check the original media's metadata if available
        duration_from_metadata = main_media.metadata.get('duration') if main_media.metadata else None
        if not (duration_from_metadata and duration_from_metadata > 0):
            logger.debug(f"Reel {reel.id}: no valid video duration found")
            return True

    # Check 3: Thumbnail variant must exist (essential for reels)
    has_thumbnail = main_media.variants.filter(variant_type='thumbnail').exists()
    if not has_thumbnail:
        logger.debug(f"Reel {reel.id}: missing thumbnail variant")
        return True

    return False