import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
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
from users.models.user import User


# ----------------------------------------------------------------------
# Input serializers
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_stories(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedStoryData.
    """
    serializer = StorySerializer(page, many=True, context={'request': request})
    data = {
        'page': paginator.page.number,
        'hasNext': paginator.page.has_next(),
        'hasPrev': paginator.page.has_previous(),
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class PaginatedStoryData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = StorySerializer(many=True)


class StoryListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedStoryData()


class StoryCreateResponseData(serializers.Serializer):
    story = StorySerializer()


class StoryCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryCreateResponseData()


class StoryDetailResponseData(serializers.Serializer):
    story = StorySerializer()


class StoryDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryDetailResponseData()


class StoryUpdateResponseData(serializers.Serializer):
    story = StorySerializer()


class StoryUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryUpdateResponseData()


class StoryDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class StoryFeedListResponseData(serializers.Serializer):
    feed = StoryFeedSerializer(many=True)
    has_next = serializers.BooleanField()
    next_offset = serializers.IntegerField(allow_null=True)


class StoryFeedListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryFeedListResponseData()


class StoryStatsResponseData(serializers.Serializer):
    stats = StoryStatsSerializer()


class StoryStatsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryStatsResponseData()


class StoryViewCountResponseData(serializers.Serializer):
    story_id = serializers.IntegerField()
    view_count = serializers.IntegerField()
    unique_viewers = serializers.IntegerField()


class StoryViewCountResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryViewCountResponseData()


class StoryDeactivateResponseData(serializers.Serializer):
    status = serializers.CharField()


class StoryDeactivateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryDeactivateResponseData()


class StoryExtendResponseData(serializers.Serializer):
    status = serializers.CharField()


class StoryExtendResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryExtendResponseData()


class StoryHighlightsResponseData(serializers.Serializer):
    highlights = StoryHighlightSerializer(many=True)


class StoryHighlightsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryHighlightsResponseData()


class StoryRecommendationsResponseData(serializers.Serializer):
    recommendations = StoryRecommendationSerializer(many=True)


class StoryRecommendationsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryRecommendationsResponseData()


class StoryCleanupResponseData(serializers.Serializer):
    deactivated = serializers.IntegerField()
    deleted = serializers.IntegerField()


class StoryCleanupResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryCleanupResponseData()


class MutualStoryViewsResponseData(serializers.Serializer):
    total_views_by_me = serializers.IntegerField()
    total_views_by_other = serializers.IntegerField()
    mutual_stories_viewed = serializers.IntegerField()
    my_unique_stories_viewed = serializers.IntegerField()
    other_unique_stories_viewed = serializers.IntegerField()


class MutualStoryViewsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MutualStoryViewsResponseData()


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


class PopularStoriesResponseData(serializers.Serializer):
    stories = PopularStorySerializer(many=True)


class PopularStoriesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PopularStoriesResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

logger = logging.getLogger(__name__)


class StoryListView(APIView):
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
        responses={200: StoryListResponseSerializer},
        description="Retrieve a paginated list of active stories (including those of followed users and public stories).",
    )
    def get(self, request):
        try:
            stories = StoryService.get_active_stories(user=request.user)
            paginator = StoriesPagination()
            page = paginator.paginate_queryset(stories, request)
            paginated_data = wrap_paginated_stories(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Stories retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error listing stories")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Storie's"],
        request={
            'multipart/form-data': StoryCreateSerializer,
        },
        responses={201: StoryCreateResponseSerializer},
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
        serializer = StoryCreateSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        story = serializer.save()
        data = StorySerializer(story, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Story created.",
                "data": {"story": data},
            },
            status=status.HTTP_201_CREATED,
        )


class StoryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return None
        return story

    @extend_schema(
        tags=["Storie's"],
        responses={200: StoryDetailResponseSerializer},
        description="Retrieve a single story by ID.",
    )
    def get(self, request, story_id):
        try:
            story = self.get_object(story_id)
            if not story:
                return Response(
                    {
                        "status": False,
                        "message": "Story not found",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            data = StorySerializer(story, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Story retrieved.",
                    "data": {"story": data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving story %s", story_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Storie's"],
        request=StoryUpdateSerializer,
        responses={200: StoryUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update story", value={"content": "Updated caption"}, request_only=True
            )
        ],
        description="Update a story (e.g., change caption). Only the owner can update.",
    )
    @transaction.atomic
    def put(self, request, story_id):
        try:
            story = self.get_object(story_id)
            if not story:
                return Response(
                    {
                        "status": False,
                        "message": "Story not found",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            if story.user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only update your own stories",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            serializer = StoryUpdateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            updated_story = serializer.update(story, serializer.validated_data)
            data = StorySerializer(updated_story, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Story updated.",
                    "data": {"story": data},
                }
            )
        except Exception as e:
            logger.exception("Error updating story %s", story_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Storie's"],
        responses={200: StoryDeleteResponseSerializer},
        description="Permanently delete a story. Only the owner can delete.",
    )
    @transaction.atomic
    def delete(self, request, story_id):
        try:
            story = self.get_object(story_id)
            if not story:
                return Response(
                    {
                        "status": False,
                        "message": "Story not found",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            if story.user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only delete your own stories",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if StoryService.delete_story(story):
                return Response(
                    {
                        "status": True,
                        "message": "Story deleted.",
                        "data": None,
                    }
                )
            return Response(
                {
                    "status": False,
                    "message": "Failed to delete story",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.exception("Error deleting story %s", story_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoryFeedView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(name="include_own", type=bool, required=False),
            OpenApiParameter(name="limit_per_user", type=int, required=False),
            OpenApiParameter(name="offset", type=int, required=False),    # idinagdag
            OpenApiParameter(name="limit", type=int, required=False),     # idinagdag
        ],
        responses={200: StoryFeedListResponseSerializer},
    )
    def get(self, request):
        try:
            include_own = request.query_params.get("include_own", "true").lower() == "true"
            limit_per_user = int(request.query_params.get("limit_per_user", 50))
            offset = int(request.query_params.get("offset", 0))
            limit = int(request.query_params.get("limit", 10))

            feed, has_next, next_offset = StoryFeedService.generate_story_feed(
                user=request.user,
                include_own_stories=include_own,
                limit_per_user=limit_per_user,
                offset=offset,
                limit=limit,
            )

            serializer = StoryFeedSerializer(feed, many=True, context={'request': request})
            response_data = {
                "feed": serializer.data,
                "has_next": has_next,
                "next_offset": next_offset,
                "total_users": len(feed)
            }
            return Response({
                "status": True,
                "message": "Story feed retrieved.",
                "data": response_data,
            })
        except Exception as e:
            logger.exception("Error generating story feed")
            return Response(
                {"status": False, "message": "Something went wrong.", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoryStatsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        responses={200: StoryStatsResponseSerializer},
        description="Get statistics about the current user's stories (total, views, etc.).",
    )
    def get(self, request):
        try:
            stats = StoryService.get_story_stats(request.user)
            return Response(
                {
                    "status": True,
                    "message": "Story statistics retrieved.",
                    "data": {"stats": stats},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving story stats")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoryViewCountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        responses={200: StoryViewCountResponseSerializer},
        description="Get total view count and unique viewers for a story. Accessible if the story is visible to the user.",
    )
    def get(self, request, story_id):
        try:
            story = StoryService.get_story_by_id(story_id)
            if not story:
                return Response(
                    {
                        "status": False,
                        "message": "Story not found",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            data = {
                "story_id": story.id,
                "view_count": ViewService.get_view_count(story),
                "unique_viewers": ViewService.get_unique_viewers(story),
            }
            return Response(
                {
                    "status": True,
                    "message": "Story view count retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving view count for story %s", story_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoryDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        responses={200: StoryDeactivateResponseSerializer},
        description="Deactivate a story (soft delete). The story will no longer appear in feeds. Only the owner can deactivate.",
    )
    @transaction.atomic
    def post(self, request, story_id):
        try:
            story = StoryService.get_story_by_id(story_id)
            if not story:
                return Response(
                    {
                        "status": False,
                        "message": "Story not found",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            if story.user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only deactivate your own stories",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            StoryService.deactivate_story(story)
            return Response(
                {
                    "status": True,
                    "message": "Story deactivated.",
                    "data": {"status": "deactivated"},
                }
            )
        except Exception as e:
            logger.exception("Error deactivating story %s", story_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoryExtendView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        request=ExtendStoryInputSerializer,
        responses={200: StoryExtendResponseSerializer},
        examples=[
            OpenApiExample(
                "Extend request", value={"additional_hours": 12}, request_only=True
            )
        ],
        description="Extend the life of an active story by a given number of hours. Only the owner can extend.",
    )
    @transaction.atomic
    def post(self, request, story_id):
        try:
            story = StoryService.get_story_by_id(story_id)
            if not story:
                return Response(
                    {
                        "status": False,
                        "message": "Story not found",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            if story.user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only extend your own stories",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = ExtendStoryInputSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            additional_hours = serializer.validated_data["additional_hours"]
            StoryService.extend_story_life(story, additional_hours=additional_hours)
            return Response(
                {
                    "status": True,
                    "message": f"Story extended by {additional_hours} hours.",
                    "data": {"status": f"Story extended by {additional_hours} hours"},
                }
            )
        except Exception as e:
            logger.exception("Error extending story %s", story_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserStoriesView(APIView):
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
        responses={200: StoryListResponseSerializer},
        description="Retrieve stories posted by a specific user (paginated).",
    )
    def get(self, request, user_id=None):
        try:
            target_user_id = user_id or request.user.id
            user = get_object_or_404(User, id=target_user_id)

            include_expired = (
                request.query_params.get("include_expired", "false").lower() == "true"
            )

            stories = StoryService.get_user_stories(
                user=user, include_expired=include_expired
            )
            paginator = StoriesPagination()
            page = paginator.paginate_queryset(stories, request)
            paginated_data = wrap_paginated_stories(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "User stories retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user stories for user %s", user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FollowingStoriesView(APIView):
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
        responses={200: StoryFeedListResponseSerializer},
        description="Get a list of stories from users followed by the current user, grouped by user.",
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 50))
            stories = StoryService.get_following_stories(user=request.user, limit=limit)
            serializer = StoryFeedSerializer(stories, many=True, context={'request': request})
            return Response(
                {
                    "status": True,
                    "message": "Following stories retrieved.",
                    "data": {"feed": serializer.data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving following stories")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoryHighlightsView(APIView):
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
        responses={200: StoryHighlightsResponseSerializer},
        description="Get highlighted stories (most viewed) for the current user.",
    )
    def get(self, request):
        try:
            days = int(request.query_params.get("days", 7))
            limit = int(request.query_params.get("limit", 10))

            highlights = StoryFeedService.get_story_highlights(
                user=request.user, days=days, limit=limit
            )
            serializer = StoryHighlightSerializer(highlights, many=True, context={'request': request})
            return Response(
                {
                    "status": True,
                    "message": "Story highlights retrieved.",
                    "data": {"highlights": serializer.data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving story highlights")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoryRecommendationsView(APIView):
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
        responses={200: StoryRecommendationsResponseSerializer},
        description="Get personalized story recommendations for the current user.",
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 5))

            recommendations = StoryFeedService.get_story_recommendations(
                user=request.user, limit=limit
            )
            serializer = StoryRecommendationSerializer(recommendations, many=True, context={'request': request})
            return Response(
                {
                    "status": True,
                    "message": "Story recommendations retrieved.",
                    "data": {"recommendations": serializer.data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving story recommendations")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoryCleanupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        request=CleanupStoriesInputSerializer,
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
        try:
            if not request.user.is_staff:
                return Response(
                    {
                        "status": False,
                        "message": "Only staff can perform cleanup",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = CleanupStoriesInputSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            deactivate_only = serializer.validated_data["deactivate_only"]
            stats = StoryService.cleanup_expired_stories(deactivate_only=deactivate_only)
            return Response(
                {
                    "status": True,
                    "message": "Cleanup completed.",
                    "data": stats,
                }
            )
        except Exception as e:
            logger.exception("Error cleaning up stories")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoriesByTypeView(APIView):
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
        responses={200: StoryListResponseSerializer},
        description="Retrieve stories filtered by type (image, video, text), with optional active filter and pagination.",
    )
    def get(self, request, story_type):
        try:
            active_only = request.query_params.get("active_only", "true").lower() == "true"
            stories = StoryService.get_stories_by_type(
                story_type=story_type, active_only=active_only
            )
            paginator = StoriesPagination()
            page = paginator.paginate_queryset(stories, request)
            paginated_data = wrap_paginated_stories(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Stories retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving stories by type %s", story_type)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MutualStoryViewsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        responses={200: MutualStoryViewsResponseSerializer},
        description="Get mutual story viewing data between the current user and another user.",
    )
    def get(self, request, other_user_id):
        try:
            other_user = get_object_or_404(User, id=other_user_id)
            stats = ViewService.get_mutual_story_views(request.user, other_user)
            return Response(
                {
                    "status": True,
                    "message": "Mutual story views retrieved.",
                    "data": stats,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving mutual story views for user %s", other_user_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PopularStoriesView(APIView):
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
        responses={200: PopularStoriesResponseSerializer},
        description="Get the most viewed stories in the last N hours.",
    )
    def get(self, request):
        try:
            hours = int(request.query_params.get("hours", 24))
            limit = int(request.query_params.get("limit", 20))

            popular_stories = StoryService.get_popular_stories(hours=hours, limit=limit)
            serializer = PopularStorySerializer(popular_stories, many=True, context={'request': request})
            return Response(
                {
                    "status": True,
                    "message": "Popular stories retrieved.",
                    "data": {"stories": serializer.data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving popular stories")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )