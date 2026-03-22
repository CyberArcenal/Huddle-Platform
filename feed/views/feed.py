# feed/views/feed.py

import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, OpenApiParameter
from core.settings.dev import LOGGER
from feed.serializers.feed import FeedRowSerializer
from feed.services.feed import FeedService

logger = logging.getLogger(__name__)


class FeedResponseSerializer(serializers.Serializer):
    """
    Direct feed response schema (no DRF paginator).
    """

    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    feed_type = serializers.CharField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    results = FeedRowSerializer(many=True)


class FeedView(APIView):
    """
    Returns the user's feed: a list of row slots with nested items.
    Posts and shares rows include per-row pagination metadata.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Feed"],
        parameters=[
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number (1-indexed) for row pagination",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of rows per page",
                required=False,
            ),
            OpenApiParameter(
                name="feed_type",
                type=str,
                location=OpenApiParameter.QUERY,
                description=(
                    "Type of feed: 'home', 'discover', 'groups', or 'stories'. "
                    "Controls which rows are included and their titles."
                ),
                required=False,
            ),
            OpenApiParameter(
                name="posts_preview",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of posts to show in the posts row",
                required=False,
            ),
            OpenApiParameter(
                name="shares_preview",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of shares to show in the shares row",
                required=False,
            ),
        ],
        responses={200: FeedResponseSerializer},
        description=(
            "Get the user's feed. Returns a list of mixed content rows "
            "(curated rows like reels, stories, events, plus filler posts/shares). "
            "Rows and titles adapt to the requested feed_type. Posts and shares "
            "rows include `pagination` metadata for lazy-loading more items."
        ),
    )
    def get(self, request):
        # Parse page and page_size
        try:
            page = int(request.query_params.get("page", 1))
        except (TypeError, ValueError):
            page = 1

        try:
            page_size = int(request.query_params.get("page_size", 10))
        except (TypeError, ValueError):
            page_size = 10

        feed_type = request.query_params.get("feed_type", "home")

        # preview sizes for posts/shares
        try:
            posts_preview = int(
                request.query_params.get(
                    "posts_preview", FeedService.DEFAULT_POSTS_PREVIEW
                )
            )
        except (TypeError, ValueError, AttributeError):
            posts_preview = FeedService.DEFAULT_POSTS_PREVIEW

        try:
            shares_preview = int(
                request.query_params.get(
                    "shares_preview", FeedService.DEFAULT_SHARES_PREVIEW
                )
            )
        except (TypeError, ValueError, AttributeError):
            shares_preview = FeedService.DEFAULT_SHARES_PREVIEW

        # Build feed rows
        try:
            feed_rows = FeedService.get_feed_rows(
                user=request.user,
                page=page,
                page_size=page_size,
                posts_preview=posts_preview,
                shares_preview=shares_preview,
                include_types=None,
                feed_type=feed_type,
            )
        except Exception as exc:
            logger.exception(
                "Failed to build feed rows for user %s: %s",
                getattr(request.user, "id", None),
                exc,
            )
            return Response({"detail": "Failed to build feed"}, status=500)

        serializer = FeedRowSerializer(
            feed_rows, many=True, context={"request": request}
        )

        # Compute hasNext/hasPrev
        hasPrev = page > 1
        hasNext = (
            len(feed_rows) == page_size
        )  # heuristic: if we filled the page, assume may next

        response = {
            "page": page,
            "page_size": page_size,
            "feed_type": feed_type,
            "hasNext": hasNext,
            "hasPrev": hasPrev,
            "results": serializer.data,
        }
        
        logger.debug(response)

        return Response(response)
