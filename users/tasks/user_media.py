# users/tasks/media.py
import logging
from celery import shared_task
from users.media_processing.user_media import UserMediaProcessingService
from users.models import UserImage

logger = logging.getLogger(__name__)

@shared_task
def process_user_image_task(user_image_id: int):
    """
    Celery task to process a UserImage asynchronously.
    """
    try:
        user_image = UserImage.objects.get(id=user_image_id)
        UserMediaProcessingService.process_image(user_image)
        logger.info(f"Successfully processed UserImage {user_image_id} via Celery")
    except UserImage.DoesNotExist:
        logger.error(f"UserImage {user_image_id} does not exist")
    except Exception as e:
        logger.exception(f"Error processing UserImage {user_image_id}: {e}")