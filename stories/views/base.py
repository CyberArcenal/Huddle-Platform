from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import StoriesPagination
from stories.serializers.base import (
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
    StoryViewCreateSerializer,
    StoryViewSerializer,
)
from django.db import transaction
from stories.services.story import StoryService
from stories.services.story_feed import StoryFeedService
from stories.services.story_view import StoryViewService
from rest_framework import serializers
from stories.serializers.base import StorySerializer, StoryViewSerializer


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


class PaginatedStoryViewSerializer(serializers.Serializer):
    """Matches the custom pagination response from StoriesPagination"""

    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = StoryViewSerializer(many=True)


# --------------------------------------------------------------


class StoryListView(APIView):
    """Get active stories or create new story"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
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
        request=StoryCreateSerializer,
        responses={201: StorySerializer},
        examples=[
            OpenApiExample(
                "Create image story",
                value={
                    "story_type": "image",
                    "media_url": "https://example.com/story.jpg",
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
        serializer = StoryCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            story = serializer.save()
            return Response(
                StorySerializer(story, context={"request": request}).data,
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

        serializer = StoryFeedSerializer(feed, many=True)
        return Response(serializer.data)


class StoryStatsView(APIView):
    """Get story statistics"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: StoryStatsSerializer},
        description="Get statistics about the current user's stories (total, views, etc.).",
    )
    def get(self, request):
        stats = StoryService.get_story_stats(request.user)
        serializer = StoryStatsSerializer(stats)
        return Response(serializer.data)


class StoryViewCreateView(APIView):
    """Record a story view"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=StoryViewCreateSerializer,
        responses={201: StoryViewSerializer},
        examples=[
            OpenApiExample("Record view", value={"story_id": 123}, request_only=True)
        ],
        description="Record that the current user has viewed a story.",
    )
    @transaction.atomic
    def post(self, request, story_id):
        serializer = StoryViewCreateSerializer(
            data={"story_id": story_id}, context={"request": request}
        )
        if serializer.is_valid():
            story_view = serializer.save()
            return Response(
                StoryViewSerializer(story_view).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StoryViewsListView(APIView):
    """Get views for a specific story"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
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
        responses={200: PaginatedStoryViewSerializer},
        description="Retrieve a paginated list of users who viewed a story. Only the story owner can access.",
    )
    def get(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {"error": "Story not found"}, status=status.HTTP_404_NOT_FOUND
            )
        # Permission check: only owner or admin can see viewers
        if story.user != request.user and not request.user.is_staff:
            return Response(
                {"error": "You do not have permission to view viewers of this story"},
                status=status.HTTP_403_FORBIDDEN,
            )
        views = StoryViewService.get_story_views(story)
        paginator = StoriesPagination()
        page = paginator.paginate_queryset(views, request)
        serializer = StoryViewSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class StoryViewCountView(APIView):
    """Get view count for a story"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
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
            "view_count": StoryViewService.get_story_view_count(story),
            "unique_viewers": StoryViewService.get_unique_viewers_count(story),
        }
        serializer = StoryViewCountSerializer(data)
        return Response(serializer.data)


class StoryRecentViewersView(APIView):
    """Get recent viewers for a story (limited list, not paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
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
                description="Maximum number of viewers",
                required=False,
            ),
        ],
        responses={200: StoryRecentViewerSerializer(many=True)},
        description="Get a list of recent viewers of a story. Only the story owner can access.",
    )
    def get(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {"error": "Story not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if story.user != request.user and not request.user.is_staff:
            return Response(
                {"error": "You do not have permission to view viewers of this story"},
                status=status.HTTP_403_FORBIDDEN,
            )
        hours = int(request.query_params.get("hours", 24))
        limit = int(request.query_params.get("limit", 50))

        viewers = StoryViewService.get_recent_viewers(story, hours=hours, limit=limit)
        serializer = StoryRecentViewerSerializer(viewers, many=True)
        return Response(serializer.data)


class StoryDeactivateView(APIView):
    """Deactivate a story (soft delete)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
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


class StoryViewStatsView(APIView):
    """Get viewing statistics for the current user"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}},
        description="Get statistics about the current user's story viewing habits (stories viewed, unique creators, etc.).",
    )
    def get(self, request):
        stats = StoryViewService.get_user_story_view_stats(request.user)
        return Response(stats)


class MutualStoryViewsView(APIView):
    """Get mutual story viewing statistics between two users"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}},
        description="Get mutual story viewing data between the current user and another user.",
    )
    def get(self, request, other_user_id):
        from users.models import User
        from django.shortcuts import get_object_or_404

        other_user = get_object_or_404(User, id=other_user_id)

        stats = StoryViewService.get_mutual_story_views(request.user, other_user)
        return Response(stats)


class PopularStoriesView(APIView):
    """Get popular stories (limited list, not paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="hours",
                type=int,
                description="Lookback period in hours",
                required=False,
            ),
            OpenApiParameter(
                name="limit", type=int, description="Number of stories", required=False
            ),
        ],
        responses={200: {"type": "array", "items": {"type": "object"}}},
        description="Get the most viewed stories in the last N hours.",
    )
    def get(self, request):
        hours = int(request.query_params.get("hours", 24))
        limit = int(request.query_params.get("limit", 20))

        popular_stories = StoryViewService.get_popular_stories(hours=hours, limit=limit)
        return Response(popular_stories)
