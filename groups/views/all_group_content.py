# groups/views/all_group_feed.py

import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers

from feed.serializers.feed import UnifiedContentItemSerializer

from feed.views.feed import FeedResponseSerializer
from groups.services.all_group_content import AllGroupContentService

logger = logging.getLogger(__name__)



class AllGroupsFeedView(APIView):
    """Feed view for all groups the current user can access"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        parameters=[
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number (1‑indexed)",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of items per page",
                required=False,
            ),
        ],
        responses={200: FeedResponseSerializer},
        description="Get all content (posts, shares, reels, events) across all groups the user can access, in chronological order.",
    )
    def get(self, request):
        # Pagination parameters
        try:
            page = int(request.query_params.get("page", 1))
        except ValueError:
            page = 1
        try:
            page_size = int(request.query_params.get("page_size", 20))
            page_size = min(page_size, 100)
        except ValueError:
            page_size = 20

        # Fetch content across all groups
        all_items = AllGroupContentService.get_all_group_content(
            requester=request.user,
            max_items=500,
        )

        # Paginate
        paginator = Paginator(all_items, page_size)
        try:
            page_obj = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.page(1)

        serializer = UnifiedContentItemSerializer(
            page_obj.object_list,
            many=True,
            context={'request': request}
        )

        data = {
            "page": page_obj.number,
            "feed_type": "all_groups",
            "page_size": page_size,
            "hasNext": page_obj.has_next(),
            "hasPrev": page_obj.has_previous(),
            "results": serializer.data,
        }
        response_data = {
            "status": True,
            "message": "All groups feed retrieved successfully.",
            "data": data,
        }
        return Response(response_data)
