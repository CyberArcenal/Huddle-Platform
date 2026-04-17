# search/views/dedicated.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
import logging

from events.serializers.event import EventSerializer
from feed.serializers.post import PostFeedSerializer
from groups.serializers.group import GroupMinimalSerializer
from search.serializers.utilities import (
    PaginatedEventSearchSerializer,
    PaginatedGroupSearchSerializer,
    PaginatedPostSearchSerializer,
    PaginatedUserSearchSerializer,
)
from search.services.content_search import SearchService
from search.services.search_history import SearchHistoryService
from users.serializers.user.minimal import UserMinimalSerializer

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to build paginated data dict (without outer envelope)
# ----------------------------------------------------------------------
def build_paginated_data(request, results_serializer, total, page, page_size):
    """
    Build the data dict that will go inside the `data` field of the response.
    """
    base_url = request.build_absolute_uri(request.path)
    query_params = request.query_params.copy()
    query_params.pop("page", None)

    def get_page_link(page_num):
        qs = query_params.copy()
        qs["page"] = page_num
        return f"{base_url}?{qs.urlencode()}"

    next_page = page + 1 if (page * page_size) < total else None
    prev_page = page - 1 if page > 1 else None

    return {
        "count": total,
        "page": page,
        "hasNext": next_page is not None,
        "hasPrev": prev_page is not None,
        "next": get_page_link(next_page) if next_page else None,
        "previous": get_page_link(prev_page) if prev_page else None,
        "results": results_serializer.data,
    }


# ----------------------------------------------------------------------
# Response serializers for each search type
# ----------------------------------------------------------------------
class SearchResponseSerializer(serializers.Serializer):
    """Generic wrapper for search responses."""
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.DictField()


class BaseSearchView(APIView):
    """
    Base class for dedicated search views.
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = None          # The serializer for the result items
    response_serializer = None       # The paginated response serializer (will be defined per view)
    search_method = None
    search_type_label = "all"

    def get(self, request):
        try:
            query = request.query_params.get("q", "").strip()
            if not query:
                return Response(
                    {
                        "status": False,
                        "message": "Search query is required",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 10))
            offset = (page - 1) * page_size

            method = getattr(SearchService, self.search_method)
            results, total = method(
                query=query,
                requesting_user=request.user if request.user.is_authenticated else None,
                limit=page_size,
                offset=offset,
            )

            # Serialize results
            serializer = self.serializer_class(results, many=True, context={"request": request})

            # Record search history
            if request.user.is_authenticated:
                try:
                    transaction.on_commit(
                        lambda: SearchHistoryService.record_search(
                            user=request.user,
                            query=query,
                            search_type=self.search_type_label,
                            results_count=total,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to record search history: {e}")

            # Build paginated data
            paginated_data = build_paginated_data(request, serializer, total, page, page_size)

            return Response(
                {
                    "status": True,
                    "message": "Search results retrieved.",
                    "data": paginated_data,
                }
            )

        except Exception as e:
            logger.error(f"Search error: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ----------------------------------------------------------------------
# Concrete search views with their own @extend_schema
# ----------------------------------------------------------------------
@extend_schema(
    tags=["Dedicated Search's"],
    parameters=[
        OpenApiParameter(
            name="q",
            type=str,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Search query",
        ),
        OpenApiParameter(
            name="page",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Page number",
        ),
        OpenApiParameter(
            name="page_size",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Results per page",
        ),
    ],
    responses={200: SearchResponseSerializer},
    description="Search users by username, email, or bio.",
)
class UserSearchView(BaseSearchView):
    serializer_class = UserMinimalSerializer  # but we don't have it imported; will need to import
    search_method = "search_users"
    search_type_label = "users"


@extend_schema(
    tags=["Dedicated Search's"],
    parameters=[
        OpenApiParameter(
            name="q",
            type=str,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Search query",
        ),
        OpenApiParameter(
            name="page",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Page number",
        ),
        OpenApiParameter(
            name="page_size",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Results per page",
        ),
    ],
    responses={200: SearchResponseSerializer},
    description="Search groups by name or description.",
)
class GroupSearchView(BaseSearchView):
    serializer_class = GroupMinimalSerializer
    search_method = "search_groups"
    search_type_label = "groups"


@extend_schema(
    tags=["Dedicated Search's"],
    parameters=[
        OpenApiParameter(
            name="q",
            type=str,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Search query",
        ),
        OpenApiParameter(
            name="page",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Page number",
        ),
        OpenApiParameter(
            name="page_size",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Results per page",
        ),
    ],
    responses={200: SearchResponseSerializer},
    description="Search events by title or description.",
)
class EventSearchView(BaseSearchView):
    serializer_class = EventSerializer
    search_method = "search_events"
    search_type_label = "events"


@extend_schema(
    tags=["Dedicated Search's"],
    parameters=[
        OpenApiParameter(
            name="q",
            type=str,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Search query",
        ),
        OpenApiParameter(
            name="page",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Page number",
        ),
        OpenApiParameter(
            name="page_size",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Results per page",
        ),
    ],
    responses={200: SearchResponseSerializer},
    description="Search posts by content.",
)
class PostSearchView(BaseSearchView):
    serializer_class = PostFeedSerializer
    search_method = "search_posts"
    search_type_label = "posts"