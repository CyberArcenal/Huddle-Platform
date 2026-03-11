import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db.models import Q

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import UsersPagination
from users.serializers.user import UserListSerializer

from ..serializers.search import (
    UserSearchSerializer,
    SearchResultSerializer,
    AdvancedSearchSerializer,
)
from ..models import User, UserStatus
from rest_framework import serializers
from ..serializers.search import SearchResultSerializer


class PaginatedSearchResultSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = SearchResultSerializer(many=True)


logger = logging.getLogger(__name__)


class UserSearchView(APIView):
    """View for searching users with basic search"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="query",
                type=str,
                description="Search term for username, email, or name",
                required=True,
            ),
            OpenApiParameter(name="page", type=int, description="Page number (default 1)", required=False),
            OpenApiParameter(name="page_size", type=int, description="Results per page (default 20, max 100)", required=False),
        ],
        responses={200: PaginatedSearchResultSerializer},
        description="Basic user search by username, email, or name.",
    )
    def get(self, request):
        logger.debug(request.data)
        serializer = UserSearchSerializer(data=request.query_params)
        if serializer.is_valid(raise_exception=True):
            try:
                users = serializer.search()
                paginator = UsersPagination()
                page = paginator.paginate_queryset(users, request)
                result_serializer = SearchResultSerializer(
                    page, many=True, context={"request": request}
                )
                return paginator.get_paginated_response(result_serializer.data)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class AdvancedUserSearchView(APIView):
    """View for advanced user search with filters"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name="username", type=str, description="Filter by username (partial match)", required=False),
            OpenApiParameter(name="email", type=str, description="Filter by email (partial match)", required=False),
            OpenApiParameter(name="first_name", type=str, description="Filter by first name (partial match)", required=False),
            OpenApiParameter(name="last_name", type=str, description="Filter by last name (partial match)", required=False),
            OpenApiParameter(name="is_verified", type=bool, description="Filter by verification status", required=False),
            OpenApiParameter(name="created_after", type=str, description="Filter users created after this datetime (ISO 8601)", required=False),
            OpenApiParameter(name="created_before", type=str, description="Filter users created before this datetime (ISO 8601)", required=False),
            OpenApiParameter(
                name="order_by",
                type=str,
                description="Order results by field (username, -username, created_at, -created_at, last_login, -last_login)",
                required=False,
            ),
            OpenApiParameter(name="page", type=int, description="Page number (default 1)", required=False),
            OpenApiParameter(name="page_size", type=int, description="Results per page (default 20, max 100)", required=False),
        ],
        responses={200: PaginatedSearchResultSerializer},
        description="Advanced user search with filters, ordering, and pagination.",
    )
    def get(self, request):
        serializer = AdvancedSearchSerializer(data=request.query_params)
        if serializer.is_valid():
            try:
                search_result = serializer.search()
                results = search_result["results"]
                paginator = UsersPagination()
                page = paginator.paginate_queryset(results, request)
                result_serializer = SearchResultSerializer(
                    page, many=True, context={"request": request}
                )
                response = paginator.get_paginated_response(result_serializer.data)
                response.data["total_count"] = search_result["total_count"]
                response.data["total_pages"] = search_result["total_pages"]
                return response
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class SearchAutocompleteView(APIView):
    """View for search autocomplete suggestions"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="query",
                type=str,
                description="Search prefix (minimum 2 characters)",
                required=True,
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "suggestions": {"type": "array", "items": {"type": "object"}},
                },
            }
        },
        examples=[
            OpenApiExample(
                "Response",
                value={
                    "query": "jo",
                    "suggestions": [
                        {
                            "id": 1,
                            "username": "john",
                            "full_name": "John Doe",
                            "type": "user",
                        },
                        {
                            "id": 2,
                            "username": "johanna",
                            "full_name": "Johanna Smith",
                            "type": "user",
                        },
                    ],
                },
                response_only=True,
            )
        ],
        description="Get autocomplete suggestions for usernames/full names based on a prefix.",
    )
    def get(self, request):
        query = request.query_params.get("query", "").strip()

        if not query or len(query) < 2:
            return Response({"query": query, "suggestions": []})

        try:
            users = User.objects.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query),
                status=UserStatus.ACTIVE,
                is_active=True,
            ).order_by("username")[:10]

            suggestions = []
            for user in users:
                suggestion = {
                    "id": user.id,
                    "username": user.username,
                    "full_name": f"{user.first_name} {user.last_name}".strip()
                    or user.username,
                    "type": "user",
                }
                if user.profile_picture:
                    suggestion["profile_picture_url"] = request.build_absolute_uri(
                        user.profile_picture.url
                    )
                suggestions.append(suggestion)

            return Response({"query": query, "suggestions": suggestions})

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SearchByUsernameView(APIView):
    """View for searching users by exact or partial username"""

    permission_classes = [permissions.IsAuthenticated]

    examples = (
        [
            OpenApiExample(
                "Exact match",
                value={
                    "match_type": "exact",
                    "results": [
                        {
                            "id": 1,
                            "username": "john",
                            "first_name": "John",
                            "last_name": "Doe",
                        }
                    ],
                },
                response_only=True,
            ),
            OpenApiExample(
                "Partial matches",
                value={
                    "match_type": "partial",
                    "count": 3,
                    "results": [
                        {
                            "id": 2,
                            "username": "john_doe",
                            "first_name": "John",
                            "last_name": "Doe",
                        },
                        {
                            "id": 3,
                            "username": "john_smith",
                            "first_name": "John",
                            "last_name": "Smith",
                        },
                        {
                            "id": 4,
                            "username": "john_wick",
                            "first_name": "John",
                            "last_name": "Wick",
                        },
                    ],
                },
                response_only=True,
            ),
        ],
    )

    def get(self, request):
        username = request.query_params.get("username", "").strip().lower()

        if not username:
            return Response(
                {"error": "Username is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            exact_match = User.objects.filter(
                username__iexact=username, status=UserStatus.ACTIVE
            ).first()

            if exact_match:
                from ..serializers.user import UserProfileSerializer

                serializer = UserProfileSerializer(
                    exact_match, context={"request": request}
                )
                return Response({"match_type": "exact", "results": [serializer.data]})

            partial_matches = User.objects.filter(
                username__icontains=username, status=UserStatus.ACTIVE
            ).order_by("username")[:20]

            from ..serializers.user import UserListSerializer

            serializer = UserListSerializer(
                partial_matches, many=True, context={"request": request}
            )

            return Response(
                {
                    "match_type": "partial",
                    "count": len(partial_matches),
                    "results": serializer.data,
                }
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SearchByEmailView(APIView):
    """View for searching users by email (admin only)"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="email", type=str, description="Email to search for", required=True
            ),
        ],
        responses={200: UserListSerializer(many=True).data},
        description="Search users by email (partial match). Admin only.",
    )
    def get(self, request):
        email = request.query_params.get("email", "").strip().lower()

        if not email:
            return Response(
                {"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            users = User.objects.filter(email__icontains=email).order_by("email")[:50]

            from ..serializers.user import UserListSerializer

            serializer = UserListSerializer(
                users, many=True, context={"request": request}
            )

            return Response(
                {"query": email, "count": len(users), "results": serializer.data}
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GlobalSearchView(APIView):
    """View for global search across multiple models (placeholder)"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                description="Search query (minimum 2 characters)",
                required=True,
            ),
        ],
        responses={200: {"type": "object"}},
        examples=[
            OpenApiExample(
                "Response",
                value={
                    "query": "python",
                    "results": {
                        "users": [
                            {
                                "id": 1,
                                "username": "pythonista",
                                "first_name": "Python",
                                "last_name": "Dev",
                            },
                            {
                                "id": 2,
                                "username": "py_dev",
                                "first_name": "Py",
                                "last_name": "Developer",
                            },
                        ],
                        "posts": [],
                        "groups": [],
                        "total": 2,
                    },
                },
                response_only=True,
            )
        ],
        description="Global search across users, posts, groups, etc. (currently only users implemented).",
    )
    def get(self, request):
        query = request.query_params.get("q", "").strip()

        if not query or len(query) < 2:
            return Response({"query": query, "results": {"users": [], "total": 0}})

        try:
            users = User.objects.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query),
                status=UserStatus.ACTIVE,
            ).order_by("username")[:10]

            from ..serializers.user import UserListSerializer

            user_serializer = UserListSerializer(
                users, many=True, context={"request": request}
            )

            return Response(
                {
                    "query": query,
                    "results": {
                        "users": user_serializer.data,
                        "users_count": len(users),
                        "total": len(users),
                    },
                }
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
