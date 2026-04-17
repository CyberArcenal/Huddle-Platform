# groups/views/feed.py

import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers

from feed.serializers.feed import UnifiedContentItemSerializer
from feed.views.feed import FeedResponseSerializer
from groups.models import Group
from groups.services.feed import GroupContentService
from groups.services.group import GroupService as GroupAccessService

logger = logging.getLogger(__name__)


class GroupFeedView(APIView):
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
        description="Get all content (posts, shares, reels, events) belonging to a group, in chronological order.",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)

        # Permission check
        if not GroupAccessService.is_user_allowed_to_view(request.user, group):
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view this group",
                    "data": None
                },
                status=403,
            )

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

        # Fetch all group content (newest first)
        all_items = GroupContentService.get_group_content(
            group=group,
            requester=request.user,
            max_items=500,  # a reasonable limit to avoid memory issues
        )

        # Paginate the list
        paginator = Paginator(all_items, page_size)
        try:
            page_obj = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            page_obj = (
                paginator.page(1) if page < 1 else paginator.page(paginator.num_pages)
            )

        # Serialize each item using UnifiedContentItemSerializer
        serializer = UnifiedContentItemSerializer(
            page_obj.object_list, many=True, context={"request": request}
        )

        # Build the response (same structure as UserContentFeedView)
        data = {
            "page": page_obj.number,
            "feed_type": "group",
            "page_size": page_size,
            "hasNext": page_obj.has_next(),
            "hasPrev": page_obj.has_previous(),
            "results": serializer.data,
        }
        response_data = {
            "status": True,
            "message": "Group feed retrieved successfully.",
            "data": data,
        }
        return Response(response_data)
