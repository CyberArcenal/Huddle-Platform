from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg, Max, Min
from analytics.models.trend_score import ObjectTrendScore
from feed.models.comment import Comment
from feed.models.reaction import Reaction
from feed.models.share import Share
from feed.models.view import ObjectView
from feed.models.bookmark import ObjectBookmark

class TrendScoreService:
    # --- CRUD ---
    @staticmethod
    def create_or_update_score(obj, score: float):
        """Create or update the trending score for a given object."""
        ct = ContentType.objects.get_for_model(obj)
        trend, _ = ObjectTrendScore.objects.update_or_create(
            content_type=ct,
            object_id=obj.id,
            defaults={"score": score},
        )
        return trend

    @staticmethod
    def delete_score(obj):
        """Delete the trending score record for an object."""
        ct = ContentType.objects.get_for_model(obj)
        ObjectTrendScore.objects.filter(content_type=ct, object_id=obj.id).delete()

    @staticmethod
    def get_score(obj):
        """Retrieve the trending score for an object, or None if missing."""
        ct = ContentType.objects.get_for_model(obj)
        trend = ObjectTrendScore.objects.filter(content_type=ct, object_id=obj.id).first()
        return trend.score if trend else None

    # --- Stats ---
    @staticmethod
    def calculate_score(obj):
        """
        Compute a trending score based on weighted metrics.
        Example formula:
        score = (likes * 1) + (comments * 2) + (shares * 3) + (views * 0.5) + (bookmarks * 2)
        Normalized by age in hours.
        """
        ct = ContentType.objects.get_for_model(obj)

        likes = Reaction.objects.filter(content_type=ct, object_id=obj.id).count()
        comments = Comment.objects.filter(content_type=ct, object_id=obj.id).count()
        shares = Share.objects.filter(content_type=ct, object_id=obj.id).count()
        views = ObjectView.objects.filter(content_type=ct, object_id=obj.id).count()
        bookmarks = ObjectBookmark.objects.filter(content_type=ct, object_id=obj.id).count()

        age_hours = max(((obj.created_at.now() - obj.created_at).total_seconds() / 3600), 1)

        score = (likes * 1) + (comments * 2) + (shares * 3) + (views * 0.5) + (bookmarks * 2)
        score = score / age_hours

        # persist
        return TrendScoreService.create_or_update_score(obj, score)

    @staticmethod
    def get_top_trending(limit=10):
        """Return the top trending objects across all content types."""
        return ObjectTrendScore.objects.order_by("-score")[:limit]

    @staticmethod
    def get_average_score():
        """Return the average trending score across all objects."""
        return ObjectTrendScore.objects.aggregate(avg=Avg("score"))["avg"] or 0

    @staticmethod
    def get_highest_score():
        """Return the highest trending score recorded."""
        return ObjectTrendScore.objects.aggregate(max=Max("score"))["max"] or 0

    @staticmethod
    def get_lowest_score():
        """Return the lowest trending score recorded."""
        return ObjectTrendScore.objects.aggregate(min=Min("score"))["min"] or 0
