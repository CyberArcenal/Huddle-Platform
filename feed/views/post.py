# feed/views/post_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
    inline_serializer,
)
from django.db import transaction
from feed.models import Post
from feed.serializers.post import (
    PostCreateSerializer,
    PostDetailSerializer,
    PostFeedSerializer,
    PostSerializer,
    PostStatisticsSerializer,
    SearchSerializer,
    UserPostStatisticsSerializer,
)
from feed.services import PostService
from global_utils.pagination import StandardResultsSetPagination
from users.models import User


# ----- Paginated response serializers for drf-spectacular -----
class PaginatedPostFeedSerializer(serializers.Serializer):
    """Matches the structure of paginator.get_paginated_response()"""

    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PostFeedSerializer(many=True)


# --------------------------------------------------------------


class PostListView(APIView):
    """View for listing and creating posts"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="Filter by user ID",
                required=False,
            ),
            OpenApiParameter(
                name="feed",
                type=bool,
                description="Get personalized feed (requires auth)",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedPostFeedSerializer},  # ✅ Fixed pagination doc
        description="List posts: public posts, posts by a specific user, or personalized feed for authenticated user.",
    )
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        user_posts = request.query_params.get("user_id")
        feed = request.query_params.get("feed", "false").lower() == "true"

        try:
            if user_posts:
                target_user = get_object_or_404(User, id=user_posts)
                posts = PostService.get_user_posts(user=target_user)
            elif feed and user:
                posts = PostService.get_feed_posts(user=user)
            else:
                posts = PostService.get_public_posts(exclude_user=user)

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(posts, request)
            serializer = PostFeedSerializer(page, many=True)
            response = paginator.get_paginated_response(serializer.data)
            return response

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(
        request=PostCreateSerializer,
        responses={201: PostSerializer},
        examples=[
            OpenApiExample(
                "Create text post",
                value={
                    "content": "Hello world!",
                    "post_type": "text",
                    "privacy": 'public',
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create image post",
                value={
                    "content": "Check out this photo",
                    "post_type": "image",
                    "media_url": "https://example.com/image.jpg",
                    "privacy": 'public',
                },
                request_only=True,
            ),
            OpenApiExample(
                "Post response",
                value={
                    "id": 123,
                    "user": 1,
                    "content": "Hello world!",
                    "post_type": "text",
                    "media_url": None,
                    "privacy": 'public',
                    "is_deleted": False,
                    "created_at": "2025-03-07T12:34:56Z",
                    "updated_at": "2025-03-07T12:34:56Z",
                },
                response_only=True,
            ),
        ],
        description="Create a new post.",
    )
    @transaction.atomic
    def post(self, request):
        """Create a new post"""
        serializer = PostSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            # Ensure user_id matches authenticated user
            if request.data.get("user_id") != request.user.id:
                return Response(
                    {"error": "Cannot create post for another user"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            post = serializer.save()
            return Response(
                PostSerializer(post, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PostDetailView(APIView):
    """View for retrieving, updating, and deleting a specific post"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_object(self, post_id):
        post = PostService.get_post_by_id(post_id)
        if not post:
            return None
        return post

    @extend_schema(
        responses={200: PostDetailSerializer},
        description="Retrieve a single post by ID.",
    )
    def get(self, request, post_id):
        post = self.get_object(post_id)
        if not post:
            return Response(
                {"error": "Post not found or deleted"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if post is public
        if not post.privacy == 'public' and request.user != post.user:
            return Response(
                {"error": "You do not have permission to view this post"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PostDetailSerializer(post, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=PostSerializer,
        responses={200: PostSerializer},
        examples=[
            OpenApiExample(
                "Update post", value={"content": "Updated content"}, request_only=True
            )
        ],
        description="Update a post (full or partial).",
    )
    @transaction.atomic
    def put(self, request, post_id):
        post = self.get_object(post_id)
        if not post:
            return Response(
                {"error": "Post not found or deleted"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check ownership
        if request.user != post.user:
            return Response(
                {"error": "You do not have permission to update this post"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PostSerializer(
            post, data=request.data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            # Ensure user_id doesn't change
            if "user_id" in request.data and request.data["user_id"] != post.user.id:
                return Response(
                    {"error": "Cannot change post owner"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            updated_post = serializer.save()
            return Response(
                PostSerializer(updated_post, context={"request": request}).data
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="hard",
                type=bool,
                description="Permanently delete instead of soft delete",
                required=False,
            ),
        ],
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        description="Delete a post (soft delete by default).",
    )
    @transaction.atomic
    def delete(self, request, post_id):
        post = self.get_object(post_id)
        if not post:
            return Response(
                {"error": "Post not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check ownership
        if request.user != post.user:
            return Response(
                {"error": "You do not have permission to delete this post"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if hard delete requested
        hard_delete = request.query_params.get("hard", "false").lower() == "true"

        success = PostService.delete_post(post, soft_delete=not hard_delete)
        if success:
            message = "Post deleted successfully"
            if hard_delete:
                message = "Post permanently deleted"
            return Response({"message": message})

        return Response(
            {"error": "Failed to delete post"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class PostStatisticsView(APIView):
    """View for post statistics"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: PostStatisticsSerializer},
        description="Get statistics for a post (like count, comment count).",
    )
    def get(self, request, post_id):
        post = get_object_or_404(Post, id=post_id, is_deleted=False)

        if not post.privacy == 'public' and request.user != post.user:
            return Response(
                {
                    "error": "You do not have permission to view statistics for this post"
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        statistics = PostService.get_post_statistics(post)
        serializer = PostStatisticsSerializer(statistics)
        return Response(serializer.data)


class UserPostStatisticsView(APIView):
    """View for user's post statistics"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (defaults to current user)",
                required=False,
            ),
        ],
        responses={200: UserPostStatisticsSerializer},
        description="Get post statistics for a user (total posts, type breakdown, etc.).",
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
        else:
            target_user = request.user

        statistics = PostService.get_user_post_statistics(target_user)
        serializer = UserPostStatisticsSerializer(statistics)
        return Response(serializer.data)


class PostSearchView(APIView):
    """View for searching posts"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="query", type=str, description="Search term", required=True
            ),
            OpenApiParameter(
                name="post_type",
                type=str,
                description="Filter by post type (text, image, video, poll)",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PaginatedPostFeedSerializer},  # ✅ Fixed pagination doc
        description="Search posts by content.",
    )
    def get(self, request):
        serializer = SearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = request.user if request.user.is_authenticated else None
        posts = PostService.search_posts(
            query=data["query"], user=user, post_type=data.get("post_type")
        )

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(posts, request)
        results = PostFeedSerializer(page, many=True).data
        return paginator.get_paginated_response(results)


class TrendingPostsView(APIView):
    """View for trending posts"""

    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="hours",
                type=int,
                description="Lookback period in hours",
                required=False,
            ),
            OpenApiParameter(
                name="min_likes",
                type=int,
                description="Minimum like count",
                required=False,
            ),
            OpenApiParameter(
                name="limit", type=int, description="Number of results", required=False
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "timeframe_hours": {"type": "integer"},
                    "min_likes": {"type": "integer"},
                    "results": {"type": "array"},
                },
            }
        },
        description="Get trending posts (most liked within a time window).",
    )
    def get(self, request):
        hours = int(request.query_params.get("hours", 24))
        min_likes = int(request.query_params.get("min_likes", 5))
        limit = int(request.query_params.get("limit", 10))

        trending = PostService.get_trending_posts(
            hours=hours, min_likes=min_likes, limit=limit
        )

        # Custom serialization for trending data
        data = []
        for item in trending:
            data.append(
                {
                    "post": PostFeedSerializer(item["post"]).data,
                    "like_count": item["like_count"],
                    "comment_count": item["comment_count"],
                }
            )

        return Response(
            {"timeframe_hours": hours, "min_likes": min_likes, "results": data}
        )


class PostRestoreView(APIView):
    """View for restoring deleted posts"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: inline_serializer(
                name="PostRestoreResponse",
                fields={
                    "message": serializers.CharField(),
                    "post": PostSerializer(),
                },
            )
        },
        description="Restore a soft-deleted post (only owner).",
    )
    @transaction.atomic
    def post(self, request, post_id):
        post = get_object_or_404(Post, id=post_id)

        # Check ownership
        if request.user != post.user:
            return Response(
                {"error": "You do not have permission to restore this post"},
                status=status.HTTP_403_FORBIDDEN,
            )

        success = PostService.restore_post(post)
        if success:
            return Response(
                {
                    "message": "Post restored successfully",
                    "post": PostSerializer(post, context={"request": request}).data,
                }
            )

        return Response(
            {"error": "Post is not deleted or could not be restored"},
            status=status.HTTP_400_BAD_REQUEST,
        )
