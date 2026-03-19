# search/views/dedicated.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
import logging

from events.serializers.event import EventSerializer
from feed.serializers.post import PostFeedSerializer
from groups.serializers.group import GroupDisplaySerializer
from search.serializers.pagination import PaginatedEventSearchSerializer, PaginatedGroupSearchSerializer, PaginatedPostSearchSerializer, PaginatedUserSearchSerializer
from search.services.content_search import SearchService
from search.services.search_history import SearchHistoryService
from search.serializers.content_serializers import (
    UserSearchSerializer
)
from rest_framework import serializers


logger = logging.getLogger(__name__)


class BaseSearchView(APIView):
    """
    Base class for dedicated search views.
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = None
    search_method = None
    search_type_label = 'all'  # for history recording

    def get(self, request):
        try:
            # 1. Get and validate query
            query = request.query_params.get('q', '').strip()
            if not query:
                return Response(
                    {'success': False, 'error': 'Search query is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 2. Get pagination params
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 10))
            offset = (page - 1) * page_size

            # 3. Perform search
            method = getattr(SearchService, self.search_method)
            results, total = method(
                query=query,
                requesting_user=request.user if request.user.is_authenticated else None,
                limit=page_size,
                offset=offset,
            )

            # 4. Serialize results
            serializer = self.serializer_class(results, many=True)

            # 5. Record search history (if authenticated)
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
                    logger.warning(f'Failed to record search history: {e}')

            # 6. Build pagination response (matching SearchPagination format)
            base_url = request.build_absolute_uri(request.path)
            query_params = request.query_params.copy()
            query_params.pop('page', None)  # remove page to build clean next/prev links

            def get_page_link(page_num):
                qs = query_params.copy()
                qs['page'] = page_num
                return f"{base_url}?{qs.urlencode()}"

            next_page = page + 1 if (page * page_size) < total else None
            prev_page = page - 1 if page > 1 else None

            response_data = {
                'count': total,
                'page': page,
                'hasNext': next_page is not None,
                'hasPrev': prev_page is not None,
                'next': get_page_link(next_page) if next_page else None,
                'previous': get_page_link(prev_page) if prev_page else None,
                'results': serializer.data,
            }

            return Response(response_data)

        except Exception as e:
            logger.error(f'Search error: {str(e)}', exc_info=True)
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@extend_schema(
    parameters=[
        OpenApiParameter(name='q', type=str, location=OpenApiParameter.QUERY, required=True, description='Search query'),
        OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY, required=False, description='Page number'),
        OpenApiParameter(name='page_size', type=int, location=OpenApiParameter.QUERY, required=False, description='Results per page'),
    ],
    responses={200: PaginatedUserSearchSerializer},
    description="Search users by username, email, or bio."
)
class UserSearchView(BaseSearchView):
    serializer_class = UserSearchSerializer
    search_method = 'search_users'
    search_type_label = 'users'


@extend_schema(
    parameters=[
        OpenApiParameter(name='q', type=str, location=OpenApiParameter.QUERY, required=True, description='Search query'),
        OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY, required=False, description='Page number'),
        OpenApiParameter(name='page_size', type=int, location=OpenApiParameter.QUERY, required=False, description='Results per page'),
    ],
    responses={200: PaginatedGroupSearchSerializer},
    description="Search groups by name or description."
)
class GroupSearchView(BaseSearchView):
    serializer_class = GroupDisplaySerializer
    search_method = 'search_groups'
    search_type_label = 'groups'


@extend_schema(
    parameters=[
        OpenApiParameter(name='q', type=str, location=OpenApiParameter.QUERY, required=True, description='Search query'),
        OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY, required=False, description='Page number'),
        OpenApiParameter(name='page_size', type=int, location=OpenApiParameter.QUERY, required=False, description='Results per page'),
    ],
    responses={200: PaginatedEventSearchSerializer},
    description="Search events by title or description."
)
class EventSearchView(BaseSearchView):
    serializer_class = EventSerializer
    search_method = 'search_events'
    search_type_label = 'events'


@extend_schema(
    parameters=[
        OpenApiParameter(name='q', type=str, location=OpenApiParameter.QUERY, required=True, description='Search query'),
        OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY, required=False, description='Page number'),
        OpenApiParameter(name='page_size', type=int, location=OpenApiParameter.QUERY, required=False, description='Results per page'),
    ],
    responses={200: PaginatedPostSearchSerializer},
    description="Search posts by content."
)
class PostSearchView(BaseSearchView):
    serializer_class = PostFeedSerializer
    search_method = 'search_posts'
    search_type_label = 'posts'