from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg,Sum
from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg, Sum, Count
from stories.models import Story
from django.utils import timezone
from feed.models.view import ObjectView
from users.models.user import User

"""
# Add a view with duration
ViewService.add_view(user=request.user, obj=post, duration=15)

# Update duration later
ViewService.update_view_duration(user=request.user, obj=post, duration=30)

# Get stats
count = ViewService.get_view_count(post)
unique = ViewService.get_unique_viewers(post)
avg_duration = ViewService.get_average_duration(post)
total_duration = ViewService.get_total_duration(post)

"""

class ViewService:
    # --- CRUD ---
    @staticmethod
    def add_view(user, obj, duration=0):
        """
        Create or update a view record for the given object.
        If user is authenticated, ensure uniqueness per user/object.
        """
        ct = ContentType.objects.get_for_model(obj)
        if user and user.is_authenticated:
            view, created = ObjectView.objects.get_or_create(
                user=user,
                content_type=ct,
                object_id=obj.id,
                defaults={"duration_seconds": duration},
            )
            if not created and duration > 0:
                view.duration_seconds += duration
                view.save()
            return view
        else:
            # Anonymous view: always create a new record
            return ObjectView.objects.create(
                user=None,
                content_type=ct,
                object_id=obj.id,
                duration_seconds=duration,
            )

    @staticmethod
    def update_view_duration(user, obj, duration):
        """
        Update duration for an existing view record.
        """
        ct = ContentType.objects.get_for_model(obj)
        qs = ObjectView.objects.filter(user=user, content_type=ct, object_id=obj.id)
        if qs.exists():
            view = qs.first()
            view.duration_seconds += duration
            view.save()
            return view
        return None

    @staticmethod
    def delete_view(user, obj):
        """
        Delete a view record for a given user/object.
        """
        ct = ContentType.objects.get_for_model(obj)
        ObjectView.objects.filter(user=user, content_type=ct, object_id=obj.id).delete()
    
    @staticmethod
    def delete_view_for_object(obj):
        """
        Delete a view record for a given user/object.
        """
        ct = ContentType.objects.get_for_model(obj)
        ObjectView.objects.filter(content_type=ct, object_id=obj.id).delete()

    # --- Stats ---
    @staticmethod
    def get_view_count(obj):
        """
        Total number of views (including anonymous).
        """
        ct = ContentType.objects.get_for_model(obj)
        return ObjectView.objects.filter(content_type=ct, object_id=obj.id).count()

    @staticmethod
    def get_unique_viewers(obj) -> int:
        """
        Count distinct authenticated users who viewed the object.
        """
        ct = ContentType.objects.get_for_model(obj)
        return (
            ObjectView.objects.filter(content_type=ct, object_id=obj.id)
            .exclude(user=None)
            .values("user")
            .distinct()
            .count()
        )

    @staticmethod
    def get_total_duration(obj):
        """
        Sum of all view durations for the object.
        """
        ct = ContentType.objects.get_for_model(obj)
        return (
            ObjectView.objects.filter(content_type=ct, object_id=obj.id)
            .aggregate(total=Sum("duration_seconds"))["total"]
            or 0
        )

    @staticmethod
    def get_average_duration(obj):
        """
        Average view duration across all views.
        """
        ct = ContentType.objects.get_for_model(obj)
        return (
            ObjectView.objects.filter(content_type=ct, object_id=obj.id)
            .aggregate(avg=Avg("duration_seconds"))["avg"]
            or 0
        )
        
    @staticmethod
    def get_popular_stories(limit=10) -> list[Story]:
        """
        Return the top N most-viewed stories (active only).
        """
        story_ct = ContentType.objects.get_for_model(Story)
        # Aggregate view counts per story
        popular = (ObjectView.objects
                   .filter(content_type=story_ct)
                   .values('object_id')
                   .annotate(view_count=Count('id'))
                   .order_by('-view_count')[:limit])
        # Extract story IDs and fetch Story objects (still active)
        story_ids = [item['object_id'] for item in popular]
        # Only include stories that are still active and not expired
        active_stories = Story.objects.filter(
            id__in=story_ids,
            is_active=True,
            expires_at__gt=timezone.now()
        )
        # Preserve order based on view_count
        ordered_stories = sorted(active_stories, key=lambda s: story_ids.index(s.id))
        return ordered_stories

    @staticmethod
    def get_user_viewed(user, limit=100) -> list[Any]:
        """
        Return the most recent objects (as ObjectView instances) viewed by the user,
        ordered by viewed_at descending.
        """
        return (ObjectView.objects
                .filter(user=user)
                .select_related('content_type')
                .order_by('-viewed_at')[:limit])

    @staticmethod
    def get_user_viewed_story(user, limit=100) -> object[User]:
        """
        Return users whose stories the current user has viewed.
        """
        story_ct = ContentType.objects.get_for_model(Story)
        # Get all stories viewed by this user
        viewed_stories = ObjectView.objects.filter(
            user=user,
            content_type=story_ct
        ).values_list('object_id', flat=True)
        # Get distinct users who own those stories, exclude self
        other_users = (Story.objects
                       .filter(id__in=viewed_stories)
                       .exclude(user=user)
                       .values_list('user', flat=True)
                       .distinct())
        # Return list of User objects (limit applied)
        return User.objects.filter(id__in=other_users)[:limit]

    @staticmethod
    def get_mutual_story_views(user, other_user) -> object[Story]:
        """
        Return stories that both users have viewed.
        """
        story_ct = ContentType.objects.get_for_model(Story)
        # Stories viewed by user
        user_stories = set(ObjectView.objects.filter(
            user=user,
            content_type=story_ct
        ).values_list('object_id', flat=True))
        # Stories viewed by other_user
        other_stories = set(ObjectView.objects.filter(
            user=other_user,
            content_type=story_ct
        ).values_list('object_id', flat=True))
        mutual_ids = user_stories.intersection(other_stories)
        return Story.objects.filter(id__in=mutual_ids)

    @staticmethod
    def get_story_views(story) -> object[ObjectView]:
        """
        Return all ObjectView records for a given story.
        """
        ct = ContentType.objects.get_for_model(story)
        return ObjectView.objects.filter(content_type=ct, object_id=story.id)

    @staticmethod
    def get_unique_viewers_count(obj) -> int:
        """
        Return the number of distinct authenticated users who viewed the object.
        """
        ct = ContentType.objects.get_for_model(obj)
        return (ObjectView.objects
                .filter(content_type=ct, object_id=obj.id)
                .exclude(user=None)
                .values('user')
                .distinct()
                .count())
    
    @staticmethod
    def has_viewed(obj, user):
        """
        Check if a user has viewed a specific object.
        """
        ct = ContentType.objects.get_for_model(obj)
        return ObjectView.objects.filter(
            user=user,
            content_type=ct,
            object_id=obj.id
        ).exists()
