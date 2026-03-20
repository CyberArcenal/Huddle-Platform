import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db.models import Q

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import UsersPagination

from ..serializers.search import (
    UserSearchSerializer,
    SearchResultSerializer,
    AdvancedSearchSerializer,
    PaginatedSearchResultSerializer,               # already existed
    AutocompleteResponseSerializer,
    SearchByUsernameResponseSerializer,
    SearchByEmailResponseSerializer,
    GlobalSearchResponseSerializer,
    AdvancedSearchPaginatedResponseSerializer,
)
from ..models import User, UserStatus

logger = logging.getLogger(__name__)


class UserSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Search's"],
        
        parameters=[
            OpenApiParameter(name="query", type=str, required=True),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: PaginatedSearchResultSerializer},
        description="Basic user search by username, email, or name.",
    )
    def get(self, request):
        serializer = UserSearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
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


class AdvancedUserSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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
        responses={200: AdvancedSearchPaginatedResponseSerializer},
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
                # Build custom paginated response with extra fields
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
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Search's"],
        
        parameters=[
            OpenApiParameter(name="query", type=str, required=True),
        ],
        responses={200: AutocompleteResponseSerializer},
        description="Get autocomplete suggestions for usernames/full names based on a prefix.",
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
    permission_classes = [permissions.IsAuthenticated]

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
                {"error": "Username is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            exact_match = User.objects.filter(
                username__iexact=username, status=UserStatus.ACTIVE
            ).first()

            if exact_match:
                # Return list with one user, using UserListSerializer for consistency
                from ..serializers.user import UserListSerializer
                serializer = UserListSerializer(
                    [exact_match], many=True, context={"request": request}
                )
                return Response({
                    "match_type": "exact",
                    "count": 1,
                    "results": serializer.data
                })

            partial_matches = User.objects.filter(
                username__icontains=username, status=UserStatus.ACTIVE
            ).order_by("username")[:20]

            from ..serializers.user import UserListSerializer
            serializer = UserListSerializer(
                partial_matches, many=True, context={"request": request}
            )
            return Response({
                "match_type": "partial",
                "count": len(partial_matches),
                "results": serializer.data
            })

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SearchByEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

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
                {"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            users = User.objects.filter(email__icontains=email).order_by("email")[:50]
            from ..serializers.user import UserListSerializer
            serializer = UserListSerializer(
                users, many=True, context={"request": request}
            )
            return Response({
                "query": email,
                "count": len(users),
                "results": serializer.data
            })

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GlobalSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Search's"],
        
        parameters=[
            OpenApiParameter(name="q", type=str, required=True),
        ],
        responses={200: GlobalSearchResponseSerializer},
        description="Global search across users, posts, groups, etc. (currently only users implemented).",
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
                        ],
                        "users_count": 1,
                        "total": 1,
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query or len(query) < 2:
            return Response({"query": query, "results": {"users": [], "users_count": 0, "total": 0}})

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
            return Response({
                "query": query,
                "results": {
                    "users": user_serializer.data,
                    "users_count": len(users),
                    "total": len(users),
                }
            })

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)