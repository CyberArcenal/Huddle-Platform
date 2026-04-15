# feed/views/user_content.py

import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.shortcuts import get_object_or_404

from feed.serializers.feed import UnifiedContentItemSerializer
from feed.services.user_content import UserContentService
from feed.views.feed import FeedResponseSerializer
from global_utils.pagination import StandardResultsSetPagination
from users.models import User
from rest_framework import serializers

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class UserContentResponseData(serializers.Serializer):
    feed_type = serializers.CharField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    results = UnifiedContentItemSerializer(many=True)


class UserContentResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserContentResponseData()


# ----------------------------------------------------------------------
# View
# ----------------------------------------------------------------------

class UserContentFeedView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

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
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Type of content to retrieve",
                required=False,
            ),
        ],
        responses={200: UserContentResponseSerializer},
        description="Get a user's activity feed (posts, shares, reels, stories) in chronological order.",
    )
    def get(self, request, user_id=None):
        # Determine target user
        if user_id is None:
            if not request.user.is_authenticated:
                return Response(
                    {
                        "status": False,
                        "message": "Authentication required",
                        "data": None,
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            target_user = request.user
        else:
            target_user = get_object_or_404(User, id=user_id)

        # Pagination parameters
        page = request.query_params.get('page', 1)
        page_size = request.query_params.get('page_size', 20)
        content_type = request.query_params.get('content_type', None)

        try:
            page = int(page)
            page_size = int(page_size)
            page_size = min(page_size, 100)
        except ValueError:
            page = 1
            page_size = 20

        # FIX: Remove the unpacking – get_user_content returns a list, not a tuple
        all_items = UserContentService.get_user_content(
            user=target_user,
            requester=request.user if request.user.is_authenticated else None,
            max_items=500,
            content_type=content_type

        )

        # Paginate the list
        paginator = Paginator(all_items, page_size)
        try:
            page_obj = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.page(1) if page < 1 else paginator.page(paginator.num_pages)

        # Serialize
        serializer = UnifiedContentItemSerializer(page_obj.object_list, many=True, context={'request': request})

        # Build response data
        response_data = {
            "feed_type": 'profile',
            "page": page_obj.number,
            "page_size": page_size,
            "hasNext": page_obj.has_next(),
            "hasPrev": page_obj.has_previous(),
            "results": serializer.data,
        }

        return Response(
            {
                "status": True,
                "message": "User content retrieved.",
                "data": response_data,
            }
        )