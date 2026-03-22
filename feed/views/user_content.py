# feed/views/user_content.py

import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.shortcuts import get_object_or_404

from feed.services.user_content import UserContentService
from feed.serializers.user_content import UnifiedContentItemSerializer
from global_utils.pagination import StandardResultsSetPagination
from users.models import User
from rest_framework import serializers

logger = logging.getLogger(__name__)


class UserContentFeedView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    class UserContentFeedResponse(serializers.Serializer):
        page = serializers.IntegerField()
        hasNext = serializers.BooleanField()
        hasPrev = serializers.BooleanField()
        count = serializers.IntegerField()
        next = serializers.URLField(allow_null=True)
        previous = serializers.URLField(allow_null=True)
        results = UnifiedContentItemSerializer(many=True)

    @extend_schema(
        tags=["User Content"],
        parameters=[
            OpenApiParameter(
                name="page",
                type=int,
                description="Page number",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Number of items per page",
                required=False,
            ),
        ],
        responses={200: UserContentFeedResponse},
        description="Get a user's activity feed (posts, shares, reels, stories) in chronological order.",
    )
    def get(self, request, user_id=None):
        # Determine target user
        if user_id is None:
            if not request.user.is_authenticated:
                return Response(
                    {"error": "Authentication required"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            target_user = request.user
        else:
            target_user = get_object_or_404(User, id=user_id)

        # Pagination parameters
        page = request.query_params.get('page', 1)
        page_size = request.query_params.get('page_size', 20)
        try:
            page = int(page)
            page_size = int(page_size)
            page_size = min(page_size, 100)  # cap at 100
        except ValueError:
            page = 1
            page_size = 20

        # Fetch all content up to a reasonable limit (e.g., 500 items)
        # We'll use cursor None and a high limit to get all items up to 500.
        # The service will merge and return a list.
        all_items, _ = UserContentService.get_user_content(
            user=target_user,
            requester=request.user if request.user.is_authenticated else None,
            limit=500,             # fetch up to 500 items from each type (or total)
        )

        # Paginate the list
        paginator = Paginator(all_items, page_size)
        try:
            page_obj = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            # Return empty page if page out of range
            page_obj = paginator.page(1) if page < 1 else paginator.page(paginator.num_pages)

        # Serialize
        serializer = UnifiedContentItemSerializer(page_obj.object_list, many=True, context={'request': request})

        # Build response using the existing pagination structure
        pagination_data = {
            "page": page_obj.number,
            "hasNext": page_obj.has_next(),
            "hasPrev": page_obj.has_previous(),
            "count": paginator.count,
            "next": None,  # we don't generate full URLs here
            "previous": None,
            "results": serializer.data,
        }
        return Response(pagination_data)