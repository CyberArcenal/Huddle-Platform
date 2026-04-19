# search/views/user_search.py
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from events.serializers.event import EventListSerializer
from feed.models.post import Post
from feed.serializers.safe_import import PostFeedSerializer
from global_utils.pagination import StandardResultsSetPagination
from groups.models.group import Group
from events.models import Event
from groups.serializers.group import GroupMinimalSerializer
from users.serializers.user.minimal import UserMinimalSerializer

from ..serializers.search import (
    UserSearchSerializer,
    AdvancedSearchSerializer,
)
from users.models import User, UserStatus

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to build paginated data dict
# ----------------------------------------------------------------------
def build_paginated_data(
    request, results_serializer, total, page, page_size, extra_fields=None
):
    """
    Build the data dict that will go inside the `data` field of the response.
    extra_fields is a dict to merge into the data dict (e.g., query, match_type, filters).
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

    data = {
        "count": total,
        "page": page,
        "hasNext": next_page is not None,
        "hasPrev": prev_page is not None,
        "next": get_page_link(next_page) if next_page else None,
        "previous": get_page_link(prev_page) if prev_page else None,
        "results": results_serializer.data,
    }
    if extra_fields:
        data.update(extra_fields)
    return data


# ----------------------------------------------------------------------
# Response serializers (for documentation)
# ----------------------------------------------------------------------
class UserSearchResponseData(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserMinimalSerializer(many=True)


class UserSearchResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserSearchResponseData()


class AdvancedUserSearchResponseData(serializers.Serializer):
    filters = serializers.DictField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserMinimalSerializer(many=True)


class AdvancedUserSearchResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = AdvancedUserSearchResponseData()


class SearchAutocompleteResponseData(serializers.Serializer):
    query = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    suggestions = UserMinimalSerializer(many=True)


class SearchAutocompleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SearchAutocompleteResponseData()


class SearchByUsernameResponseData(serializers.Serializer):
    match_type = serializers.ChoiceField(choices=["exact", "partial"])
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserMinimalSerializer(many=True)


class SearchByUsernameResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SearchByUsernameResponseData()


class SearchByEmailResponseData(serializers.Serializer):
    query = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserMinimalSerializer(many=True)


class SearchByEmailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SearchByEmailResponseData()


class GlobalSearchResponseData(serializers.Serializer):
    query = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    users = UserMinimalSerializer(many=True)
    users_count = serializers.IntegerField()
    posts = PostFeedSerializer(many=True)
    posts_count = serializers.IntegerField(required=False)
    groups = GroupMinimalSerializer(many=True)
    groups_count = serializers.IntegerField(required=False)
    events = EventListSerializer(many=True)
    events_count = serializers.IntegerField(required=False)
    total = serializers.IntegerField()


class GlobalSearchResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GlobalSearchResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------


class UserSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=["User Search's"],
        parameters=[
            OpenApiParameter(name="query", type=str, required=True),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: UserSearchResponseSerializer},
        description="Basic user search by username, email, or name.",
    )
    def get(self, request):
        serializer = UserSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        paginator = self.pagination_class()
        try:
            users = serializer.search()
            page = paginator.paginate_queryset(users, request)
            result_serializer = UserMinimalSerializer(
                page, many=True, context={"request": request}
            )

            # Build paginated data manually
            total = users.count()
            page_number = paginator.page.number
            page_size = paginator.page_size

            base_url = request.build_absolute_uri(request.path)
            query_params = request.query_params.copy()
            query_params.pop("page", None)

            def get_page_link(page_num):
                qs = query_params.copy()
                qs["page"] = page_num
                return f"{base_url}?{qs.urlencode()}"

            next_page = page_number + 1 if (page_number * page_size) < total else None
            prev_page = page_number - 1 if page_number > 1 else None

            paginated_data = {
                "count": total,
                "page": page_number,
                "hasNext": next_page is not None,
                "hasPrev": prev_page is not None,
                "next": get_page_link(next_page) if next_page else None,
                "previous": get_page_link(prev_page) if prev_page else None,
                "results": result_serializer.data,
            }

            return Response(
                {
                    "status": True,
                    "message": "User search results retrieved.",
                    "data": paginated_data,
                }
            )

        except Exception as e:
            logger.exception("UserSearchView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class AdvancedUserSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=["User Search's"],
        parameters=[
            OpenApiParameter(name="username", type=str, required=False),
            OpenApiParameter(name="email", type=str, required=False),
            OpenApiParameter(name="first_name", type=str, required=False),
            OpenApiParameter(name="last_name", type=str, required=False),
            OpenApiParameter(name="is_verified", type=bool, required=False),
            OpenApiParameter(name="created_after", type=str, required=False),
            OpenApiParameter(name="created_before", type=str, required=False),
            OpenApiParameter(name="order_by", type=str, required=False),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: AdvancedUserSearchResponseSerializer},
        description="Advanced user search with filters, ordering, and pagination.",
    )
    def get(self, request):
        serializer = AdvancedSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        paginator = self.pagination_class()
        try:
            queryset = serializer.get_queryset()
            total = queryset.count()
            page = paginator.paginate_queryset(queryset, request)
            result_serializer = UserMinimalSerializer(
                page, many=True, context={"request": request}
            )

            # Build paginated data
            page_number = paginator.page.number
            page_size = paginator.page_size
            base_url = request.build_absolute_uri(request.path)
            query_params = request.query_params.copy()
            query_params.pop("page", None)

            def get_page_link(page_num):
                qs = query_params.copy()
                qs["page"] = page_num
                return f"{base_url}?{qs.urlencode()}"

            next_page = page_number + 1 if (page_number * page_size) < total else None
            prev_page = page_number - 1 if page_number > 1 else None

            paginated_data = {
                "filters": request.query_params.dict(),
                "count": total,
                "page": page_number,
                "hasNext": next_page is not None,
                "hasPrev": prev_page is not None,
                "next": get_page_link(next_page) if next_page else None,
                "previous": get_page_link(prev_page) if prev_page else None,
                "results": result_serializer.data,
            }

            return Response(
                {
                    "status": True,
                    "message": "Advanced user search results retrieved.",
                    "data": paginated_data,
                }
            )

        except Exception as e:
            logger.exception("AdvancedUserSearchView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class SearchAutocompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=["User Search's"],
        parameters=[
            OpenApiParameter(name="query", type=str, required=True),
        ],
        responses={200: SearchAutocompleteResponseSerializer},
        description="Get autocomplete suggestions for usernames/full names based on a prefix.",
    )
    def get(self, request):
        query = request.query_params.get("query", "").strip()
        if not query or len(query) < 2:
            # Return empty result with success
            return Response(
                {
                    "status": True,
                    "message": "Query too short.",
                    "data": {
                        "query": query,
                        "count": 0,
                        "page": 1,
                        "hasNext": False,
                        "hasPrev": False,
                        "next": None,
                        "previous": None,
                        "suggestions": [],
                    },
                },
                status=status.HTTP_200_OK,
            )

        paginator = self.pagination_class()
        try:
            users = User.objects.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query),
                status=UserStatus.ACTIVE,
                is_active=True,
            ).order_by("username")

            total = users.count()
            page = paginator.paginate_queryset(users, request)
            result_serializer = UserMinimalSerializer(
                page, many=True, context={"request": request}
            )

            page_number = paginator.page.number
            page_size = paginator.page_size
            base_url = request.build_absolute_uri(request.path)
            query_params = request.query_params.copy()
            query_params.pop("page", None)

            def get_page_link(page_num):
                qs = query_params.copy()
                qs["page"] = page_num
                return f"{base_url}?{qs.urlencode()}"

            next_page = page_number + 1 if (page_number * page_size) < total else None
            prev_page = page_number - 1 if page_number > 1 else None

            paginated_data = {
                "query": query,
                "count": total,
                "page": page_number,
                "hasNext": next_page is not None,
                "hasPrev": prev_page is not None,
                "next": get_page_link(next_page) if next_page else None,
                "previous": get_page_link(prev_page) if prev_page else None,
                "suggestions": result_serializer.data,
            }

            return Response(
                {
                    "status": True,
                    "message": "Autocomplete suggestions retrieved.",
                    "data": paginated_data,
                }
            )

        except Exception as e:
            logger.exception("SearchAutocompleteView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class SearchByUsernameView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=["User Search's"],
        parameters=[
            OpenApiParameter(name="username", type=str, required=True),
        ],
        responses={200: SearchByUsernameResponseSerializer},
        description="Search users by exact or partial username.",
    )
    def get(self, request):
        username = request.query_params.get("username", "").strip().lower()
        if not username:
            return Response(
                {
                    "status": False,
                    "message": "Username is required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        paginator = self.pagination_class()
        try:
            exact_match = User.objects.filter(
                username__iexact=username, status=UserStatus.ACTIVE
            )

            if exact_match.exists():
                page = paginator.paginate_queryset(exact_match, request)
                result_serializer = UserMinimalSerializer(
                    page, many=True, context={"request": request}
                )
                total = exact_match.count()
                page_number = paginator.page.number
                page_size = paginator.page_size
                base_url = request.build_absolute_uri(request.path)
                query_params = request.query_params.copy()
                query_params.pop("page", None)

                def get_page_link(page_num):
                    qs = query_params.copy()
                    qs["page"] = page_num
                    return f"{base_url}?{qs.urlencode()}"

                next_page = (
                    page_number + 1 if (page_number * page_size) < total else None
                )
                prev_page = page_number - 1 if page_number > 1 else None

                paginated_data = {
                    "match_type": "exact",
                    "count": total,
                    "page": page_number,
                    "hasNext": next_page is not None,
                    "hasPrev": prev_page is not None,
                    "next": get_page_link(next_page) if next_page else None,
                    "previous": get_page_link(prev_page) if prev_page else None,
                    "results": result_serializer.data,
                }
                return Response(
                    {
                        "status": True,
                        "message": "User search results retrieved.",
                        "data": paginated_data,
                    }
                )

            partial_matches = User.objects.filter(
                username__icontains=username, status=UserStatus.ACTIVE
            ).order_by("username")

            page = paginator.paginate_queryset(partial_matches, request)
            result_serializer = UserMinimalSerializer(
                page, many=True, context={"request": request}
            )
            total = partial_matches.count()
            page_number = paginator.page.number
            page_size = paginator.page_size
            base_url = request.build_absolute_uri(request.path)
            query_params = request.query_params.copy()
            query_params.pop("page", None)

            def get_page_link(page_num):
                qs = query_params.copy()
                qs["page"] = page_num
                return f"{base_url}?{qs.urlencode()}"

            next_page = page_number + 1 if (page_number * page_size) < total else None
            prev_page = page_number - 1 if page_number > 1 else None

            paginated_data = {
                "match_type": "partial",
                "count": total,
                "page": page_number,
                "hasNext": next_page is not None,
                "hasPrev": prev_page is not None,
                "next": get_page_link(next_page) if next_page else None,
                "previous": get_page_link(prev_page) if prev_page else None,
                "results": result_serializer.data,
            }
            return Response(
                {
                    "status": True,
                    "message": "User search results retrieved.",
                    "data": paginated_data,
                }
            )

        except Exception as e:
            logger.exception("SearchByUsernameView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class SearchByEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=["User Search's"],
        parameters=[
            OpenApiParameter(name="email", type=str, required=True),
        ],
        responses={200: SearchByEmailResponseSerializer},
        description="Search users by email (partial match). Admin only.",
    )
    def get(self, request):
        email = request.query_params.get("email", "").strip().lower()
        if not email:
            return Response(
                {
                    "status": False,
                    "message": "Email is required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        paginator = self.pagination_class()
        try:
            users = User.objects.filter(email__icontains=email).order_by("email")
            total = users.count()
            page = paginator.paginate_queryset(users, request)
            result_serializer = UserMinimalSerializer(
                page, many=True, context={"request": request}
            )

            page_number = paginator.page.number
            page_size = paginator.page_size
            base_url = request.build_absolute_uri(request.path)
            query_params = request.query_params.copy()
            query_params.pop("page", None)

            def get_page_link(page_num):
                qs = query_params.copy()
                qs["page"] = page_num
                return f"{base_url}?{qs.urlencode()}"

            next_page = page_number + 1 if (page_number * page_size) < total else None
            prev_page = page_number - 1 if page_number > 1 else None

            paginated_data = {
                "query": email,
                "count": total,
                "page": page_number,
                "hasNext": next_page is not None,
                "hasPrev": prev_page is not None,
                "next": get_page_link(next_page) if next_page else None,
                "previous": get_page_link(prev_page) if prev_page else None,
                "results": result_serializer.data,
            }

            return Response(
                {
                    "status": True,
                    "message": "Email search results retrieved.",
                    "data": paginated_data,
                }
            )

        except Exception as e:
            logger.exception("SearchByEmailView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class GlobalSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=["Global Search"],
        parameters=[
            OpenApiParameter(name="q", type=str, required=True),
        ],
        responses={200: GlobalSearchResponseSerializer},
        description="Global search across users, posts, groups, events, etc.",
    )
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query or len(query) < 2:
            # Return empty result
            empty_data = {
                "query": query,
                "count": 0,
                "page": 1,
                "hasNext": False,
                "hasPrev": False,
                "next": None,
                "previous": None,
                "users": [],
                "users_count": 0,
                "posts": [],
                "posts_count": 0,
                "groups": [],
                "groups_count": 0,
                "events": [],
                "events_count": 0,
                "total": 0,
            }
            return Response(
                {
                    "status": True,
                    "message": "Query too short.",
                    "data": empty_data,
                },
                status=status.HTTP_200_OK,
            )

        paginator = self.pagination_class()
        try:
            # Users
            users = User.objects.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query),
                status=UserStatus.ACTIVE,
            ).order_by("username")
            page = paginator.paginate_queryset(users, request)
            user_serializer = UserMinimalSerializer(
                page, many=True, context={"request": request}
            )

            # Posts
            posts = Post.objects.filter(
                Q(content__icontains=query), is_deleted=False
            ).order_by("-created_at")[:10]
            post_data = PostFeedSerializer(
                posts, many=True, context={"request": request}
            )

            # Groups
            groups = Group.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            ).order_by("name")[:10]
            group_data = GroupMinimalSerializer(
                groups, many=True, context={"request": request}
            )

            # Events
            events = Event.objects.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(location__icontains=query)
            ).order_by("-start_time")[:10]
            event_data = EventListSerializer(
                events, many=True, context={"request": request}
            )

            total_users = users.count()
            page_number = paginator.page.number
            page_size = paginator.page_size
            base_url = request.build_absolute_uri(request.path)
            query_params = request.query_params.copy()
            query_params.pop("page", None)

            def get_page_link(page_num):
                qs = query_params.copy()
                qs["page"] = page_num
                return f"{base_url}?{qs.urlencode()}"

            next_page = (
                page_number + 1 if (page_number * page_size) < total_users else None
            )
            prev_page = page_number - 1 if page_number > 1 else None

            paginated_data = {
                "query": query,
                "count": total_users,
                "page": page_number,
                "hasNext": next_page is not None,
                "hasPrev": prev_page is not None,
                "next": get_page_link(next_page) if next_page else None,
                "previous": get_page_link(prev_page) if prev_page else None,
                "users": user_serializer.data,
                "users_count": total_users,
                "posts": post_data.data,
                "posts_count": len(posts),
                "groups": group_data.data,
                "groups_count": len(groups),
                "events": event_data.data,
                "events_count": len(events),
                "total": total_users + len(posts) + len(groups) + len(events),
            }

            return Response(
                {
                    "status": True,
                    "message": "Global search results retrieved.",
                    "data": paginated_data,
                }
            )

        except Exception as e:
            logger.exception("GlobalSearchView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
