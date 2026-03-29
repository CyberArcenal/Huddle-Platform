import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from feed.serializers.view import ViewMinimalSerializer
from feed.services.view import ViewService
from global_utils.pagination import StoriesPagination
from stories.serializers.story import (
    StoryCleanupResponseSerializer,
    StoryCreateSerializer,
    StoryFeedSerializer,
    StoryHighlightSerializer,
    StoryRecentViewerSerializer,
    StoryRecommendationSerializer,
    StorySerializer,
    StoryStatsSerializer,
    StoryUpdateSerializer,
    StoryViewCountSerializer,
)
from django.db import transaction
from stories.services.story import StoryService
from stories.services.story_feed import StoryFeedService
from rest_framework import serializers
from stories.serializers.story import StorySerializer
from users.models.user import User


# ----- New input serializers for endpoints that previously used raw dicts -----
class ExtendStoryInputSerializer(serializers.Serializer):
    additional_hours = serializers.IntegerField(
        default=24,
        min_value=1,
        max_value=168,
        help_text="Number of hours to extend the story life (max 7 days)",
    )


class CleanupStoriesInputSerializer(serializers.Serializer):
    deactivate_only = serializers.BooleanField(
        default=True,
        help_text="If True, only deactivate expired stories; if False, delete them permanently",
    )


# ------------------------------------------------------------------------------


# ----- Paginated response serializers for drf-spectacular -----
class PaginatedStorySerializer(serializers.Serializer):
    """Matches the custom pagination response from StoriesPagination"""

    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = StorySerializer(many=True)


# --------------------------------------------------------------

logger = logging.getLogger(__name__)


class StoryListView(APIView):
    """Get active stories or create new story"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedStorySerializer},
        description="Retrieve a paginated list of active stories (including those of followed users and public stories).",
    )
    def get(self, request):
        """Get active stories"""
        stories = StoryService.get_active_stories(user=request.user)
        paginator = StoriesPagination()
        page = paginator.paginate_queryset(stories, request)
        serializer = StorySerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Storie's"],
                 request={
            'multipart/form-data': StoryCreateSerializer,
        },
        responses={201: StorySerializer},
        examples=[
            OpenApiExample(
                "Create image story",
                value={
                    "story_type": "image",
                    "media_file": "(binary file upload)",
                    "content": "Optional caption",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create text story",
                value={"story_type": "text", "content": "Just a thought..."},
                request_only=True,
            ),
        ],
        description="Create a new story. The story will be active for 24 hours.",
    )
    @transaction.atomic
    def post(self, request):
        """Create new story"""
        logger.debug(request.data)
        serializer = StoryCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid(raise_exception=True):
            story = serializer.save()
            data = StorySerializer(story, context={"request": request}).data
            # logger.debug(data)
            return Response(
                data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StoryDetailView(APIView):
    """Get, update, or delete a specific story"""

    permission_classes = [IsAuthenticated]

    def get_object(self, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return None
        return story

    @extend_schema(
        tags=["Storie's"],
        responses={200: StorySerializer}, description="Retrieve a single story by ID."
    )
    def get(self, request, story_id):
        story = self.get_object(story_id)
        if not story:
            return Response(
                {"error": "Story not found"}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = StorySerializer(story, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["Storie's"],
        request=StoryUpdateSerializer,
        responses={200: StorySerializer},
        examples=[
            OpenApiExample(
                "Update story", value={"content": "Updated caption"}, request_only=True
            )
        ],
        description="Update a story (e.g., change caption). Only the owner can update.",
    )
    @transaction.atomic
    def put(self, request, story_id):
        story = self.get_object(story_id)
        if not story:
            return Response(
                {"error": "Story not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if story.user != request.user:
            return Response(
                {"error": "You can only update your own stories"},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = StoryUpdateSerializer(data=request.data)
        if serializer.is_valid():
            updated_story = serializer.update(story, serializer.validated_data)
            return Response(
                StorySerializer(updated_story, context={"request": request}).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["Storie's"],
        responses={
            200: {"type": "object", "properties": {"status": {"type": "string"}}}
        },
        description="Permanently delete a story. Only the owner can delete.",
    )
    @transaction.atomic
    def delete(self, request, story_id):
        story = self.get_object(story_id)
        if not story:
            return Response(
                {"error": "Story not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if story.user != request.user:
            return Response(
                {"error": "You can only delete your own stories"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if StoryService.delete_story(story):
            return Response({"status": "Story deleted"})
        return Response(
            {"error": "Failed to delete story"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class StoryFeedView(APIView):
    """Get personalized story feed (structured, not paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="include_own",
                type=bool,
                description="Include user's own stories",
                required=False,
            ),
            OpenApiParameter(
                name="limit_per_user",
                type=int,
                description="Max stories per user",
                required=False,
            ),
            OpenApiParameter(
                name="max_users",
                type=int,
                description="Max number of users to include",
                required=False,
            ),
        ],
        responses={200: StoryFeedSerializer(many=True)},
        description="Generate a personalized story feed grouped by user.",
    )
    def get(self, request):
        include_own = request.query_params.get("include_own", "true").lower() == "true"
        limit_per_user = int(request.query_params.get("limit_per_user", 3))
        max_users = int(request.query_params.get("max_users", 20))

        feed = StoryFeedService.generate_story_feed(
            user=request.user,
            include_own_stories=include_own,
            limit_per_user=limit_per_user,
            max_users=max_users,
        )

        serializer = StoryFeedSerializer(feed, many=True, context={'request': request})
        return Response(serializer.data)


class StoryStatsView(APIView):
    """Get story statistics"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        responses={200: StoryStatsSerializer},
        description="Get statistics about the current user's stories (total, views, etc.).",
    )
    def get(self, request):
        stats = StoryService.get_story_stats(request.user)
        serializer = StoryStatsSerializer(stats)
        return Response(serializer.data)


class StoryViewCountView(APIView):
    """Get view count for a story"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        responses={200: StoryViewCountSerializer},
        description="Get total view count and unique viewers for a story. Accessible if the story is visible to the user.",
    )
    def get(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {"error": "Story not found"}, status=status.HTTP_404_NOT_FOUND
            )
        data = {
            "story_id": story.id,
            "view_count": ViewService.get_view_count(story),
            "unique_viewers": ViewService.get_unique_viewers(story),
        }
        serializer = StoryViewCountSerializer(data)
        return Response(serializer.data)


class StoryDeactivateView(APIView):
    """Deactivate a story (soft delete)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        responses={
            200: {"type": "object", "properties": {"status": {"type": "string"}}}
        },
        description="Deactivate a story (soft delete). The story will no longer appear in feeds. Only the owner can deactivate.",
    )
    @transaction.atomic
    def post(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {"error": "Story not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if story.user != request.user:
            return Response(
                {"error": "You can only deactivate your own stories"},
                status=status.HTTP_403_FORBIDDEN,
            )
        StoryService.deactivate_story(story)
        return Response({"status": "Story deactivated"})


class StoryExtendView(APIView):
    """Extend story expiration"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        request=ExtendStoryInputSerializer,  # ✅ Now using proper serializer
        responses={
            200: {"type": "object", "properties": {"status": {"type": "string"}}}
        },
        examples=[
            OpenApiExample(
                "Extend request", value={"additional_hours": 12}, request_only=True
            )
        ],
        description="Extend the life of an active story by a given number of hours. Only the owner can extend.",
    )
    @transaction.atomic
    def post(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {"error": "Story not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if story.user != request.user:
            return Response(
                {"error": "You can only extend your own stories"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ExtendStoryInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        additional_hours = serializer.validated_data["additional_hours"]
        StoryService.extend_story_life(story, additional_hours=additional_hours)
        return Response({"status": f"Story extended by {additional_hours} hours"})


class UserStoriesView(APIView):
    """Get stories for a specific user"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="include_expired",
                type=bool,
                description="Include expired stories",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedStorySerializer},
        description="Retrieve stories posted by a specific user (paginated).",
    )
    def get(self, request, user_id=None):
        target_user_id = user_id or request.user.id
        from users.models import User
        from django.shortcuts import get_object_or_404

        user = get_object_or_404(User, id=target_user_id)

        include_expired = (
            request.query_params.get("include_expired", "false").lower() == "true"
        )

        stories = StoryService.get_user_stories(
            user=user, include_expired=include_expired
        )
        paginator = StoriesPagination()
        page = paginator.paginate_queryset(stories, request)
        serializer = StorySerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class FollowingStoriesView(APIView):
    """Get stories from followed users (structured feed, not paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Maximum number of stories to return",
                required=False,
            ),
        ],
        responses={200: StoryFeedSerializer(many=True)},
        description="Get a list of stories from users followed by the current user, grouped by user.",
    )
    def get(self, request):
        limit = int(request.query_params.get("limit", 50))

        stories = StoryService.get_following_stories(user=request.user, limit=limit)
        serializer = StoryFeedSerializer(stories, many=True)
        return Response(serializer.data)


class StoryHighlightsView(APIView):
    """Get story highlights (limited list, not paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                description="Number of days to look back",
                required=False,
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of highlights",
                required=False,
            ),
        ],
        responses={200: StoryHighlightSerializer(many=True)},
        description="Get highlighted stories (most viewed) for the current user.",
    )
    def get(self, request):
        days = int(request.query_params.get("days", 7))
        limit = int(request.query_params.get("limit", 10))

        highlights = StoryFeedService.get_story_highlights(
            user=request.user, days=days, limit=limit
        )
        serializer = StoryHighlightSerializer(highlights, many=True)
        return Response(serializer.data)


class StoryRecommendationsView(APIView):
    """Get story recommendations (limited list, not paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of recommendations",
                required=False,
            ),
        ],
        responses={200: StoryRecommendationSerializer(many=True)},
        description="Get personalized story recommendations for the current user.",
    )
    def get(self, request):
        limit = int(request.query_params.get("limit", 5))

        recommendations = StoryFeedService.get_story_recommendations(
            user=request.user, limit=limit
        )
        serializer = StoryRecommendationSerializer(recommendations, many=True)
        return Response(serializer.data)


class StoryCleanupView(APIView):
    """Cleanup expired stories (admin only)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        request=CleanupStoriesInputSerializer,  # ✅ Now using proper serializer
        responses={200: StoryCleanupResponseSerializer},
        examples=[
            OpenApiExample(
                "Cleanup response",
                value={"deactivated": 5, "deleted": 2},
                response_only=True,
            )
        ],
        description="Admin endpoint to clean up expired stories (deactivate or delete).",
    )
    @transaction.atomic
    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "Only staff can perform cleanup"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CleanupStoriesInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        deactivate_only = serializer.validated_data["deactivate_only"]
        stats = StoryService.cleanup_expired_stories(deactivate_only=deactivate_only)
        output_serializer = StoryCleanupResponseSerializer(stats)
        return Response(output_serializer.data)


class StoriesByTypeView(APIView):
    """Get stories by type"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="active_only",
                type=bool,
                description="Only active stories",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedStorySerializer},
        description="Retrieve stories filtered by type (image, video, text), with optional active filter and pagination.",
    )
    def get(self, request, story_type):
        active_only = request.query_params.get("active_only", "true").lower() == "true"

        stories = StoryService.get_stories_by_type(
            story_type=story_type, active_only=active_only
        )
        paginator = StoriesPagination()
        page = paginator.paginate_queryset(stories, request)
        serializer = StorySerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


# ------------------ Response Serializer ------------------
class StoryViewStatsResponseSerializer(serializers.Serializer):
    total_views = serializers.IntegerField()
    unique_creators_viewed = serializers.IntegerField()
    total_stories_viewed = serializers.IntegerField()
    active_stories_viewed = serializers.IntegerField()
    expired_stories_viewed = serializers.IntegerField()


# ------------------ Response Serializer ------------------
class MutualStoryViewsResponseSerializer(serializers.Serializer):
    total_views_by_me = serializers.IntegerField()
    total_views_by_other = serializers.IntegerField()
    mutual_stories_viewed = serializers.IntegerField()
    my_unique_stories_viewed = serializers.IntegerField()
    other_unique_stories_viewed = serializers.IntegerField()


# ------------------ API View ------------------
class MutualStoryViewsView(APIView):
    """Get mutual story viewing statistics between two users"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        responses={200: MutualStoryViewsResponseSerializer},
        description="Get mutual story viewing data between the current user and another user.",
    )
    def get(self, request, other_user_id):
        other_user = get_object_or_404(User, id=other_user_id)
        stats = ViewService.get_mutual_story_views(request.user, other_user)
        serializer = MutualStoryViewsResponseSerializer(stats)
        return Response(serializer.data)



# ------------------ Response Serializer ------------------
class PopularStorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    story_type = serializers.CharField()
    content = serializers.CharField(allow_null=True, required=False)
    media_url = serializers.CharField(allow_null=True, required=False)
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    total_views = serializers.IntegerField()


# ------------------ API View ------------------
class PopularStoriesView(APIView):
    """Get popular stories (limited list, not paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="hours",
                type=int,
                description="Lookback period in hours",
                required=False,
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of stories",
                required=False,
            ),
        ],
        responses={200: PopularStorySerializer(many=True)},
        description="Get the most viewed stories in the last N hours.",
    )
    def get(self, request):
        hours = int(request.query_params.get("hours", 24))
        limit = int(request.query_params.get("limit", 20))

        popular_stories = StoryService.get_popular_stories(hours=hours, limit=limit)
        serializer = PopularStorySerializer(popular_stories, many=True)
        return Response(serializer.data)

