import logging

logger = logging.getLogger(__name__)


def log_story_deactivated(story, views_deleted=0):
    logger.info(f"Story {story.id} deactivated. {views_deleted} views deleted.")


def log_story_reactivated(story):
    logger.info(f"Story {story.id} reactivated.")