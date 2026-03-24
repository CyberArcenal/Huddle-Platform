# feed/views/user_liked_items_view.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.shortcuts import get_object_or_404
from feed.services.user_liked_items import UserLikedItemsService
from feed.views.feed import FeedResponseSerializer
from users.models import User
from feed.serializers.feed import UnifiedContentItemSerializer
from global_utils.pagination import StandardResultsSetPagination
from drf_spectacular.utils import extend_schema, OpenApiParameter
class UserLikedItemsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["User Content"],
        parameters=[
            OpenApiParameter(
                name="page",
                description="Page number (1-indexed) for pagination",
                required=False,
                type=int,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="page_size",
                description="Number of items per page (capped by server max)",
                required=False,
                type=int,
                location=OpenApiParameter.QUERY,
            ),
            # If your route includes user_id as a path param, declare it in your urls.py and add it here as PATH.
        ],
        responses={200: FeedResponseSerializer},
        description="Get items (posts, reels, comments, user images) that the user has reacted to. Returns feed-compatible rows using the same UnifiedContentItemSerializer structure.",
    )
    def get(self, request, user_id=None):
        # Determine target user
        if user_id is None:
            if not request.user.is_authenticated:
                return Response({"error": "Authentication required"}, status=401)
            target_user = request.user
        else:
            target_user = get_object_or_404(User, id=user_id)

        paginator = StandardResultsSetPagination()
        try:
            page = int(request.query_params.get('page', 1))
        except (TypeError, ValueError):
            page = 1

        try:
            page_size = int(request.query_params.get('page_size', paginator.page_size))
        except (TypeError, ValueError):
            page_size = paginator.page_size

        page_size = min(page_size, getattr(paginator, "max_page_size", page_size))

        items, total = UserLikedItemsService.get_liked_items(
            target_user=target_user,
            requester=(request.user if request.user.is_authenticated else None),
            page=page,
            page_size=page_size
        )

        # items already in the form [{"type": "<feed_type>", "item": <model instance>}, ...]
        serializer = UnifiedContentItemSerializer(items, many=True, context={'request': request})
        serialized_items = serializer.data

        response = {
            "count": total,
            "page": page,
            "hasNext": (page * page_size) < total,
            "hasPrev": page > 1,
            "next": None,
            "previous": None,
            "results": serialized_items,
        }
        return Response(response)
