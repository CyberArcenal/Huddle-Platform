# feed/views/comment_views.py

import logging

from rest_framework.views import APIView, settings
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from feed.models import Comment, Post
from feed.serializers.comment import CommentCreateSerializer, CommentDisplaySerializer
from feed.services import CommentService
from global_utils.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


# ----- Paginated response serializers for drf-spectacular -----
class PaginatedCommentSerializer(serializers.Serializer):
    """Matches the structure of paginator.get_paginated_response()"""

    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = CommentDisplaySerializer(many=True)


# --------------------------------------------------------------


class CommentListView(APIView):
    """View for listing and creating comments"""

    def get_permissions(self):
        """Set permissions based on request method"""
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["Comment's"],
        parameters=[
            # post_id is a path parameter, not query
            OpenApiParameter(
                name="post_id",
                type=int,
                description="ID of the post to get comments for",
                required=False,
                location=OpenApiParameter.PATH,
            ),
            OpenApiParameter(
                name="include_replies",
                type=bool,
                description="Include nested replies",
                required=False,
            ),
            OpenApiParameter(
                name="include_deleted",
                type=bool,
                description="Include soft-deleted comments (admin only)",
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
        responses={200: PaginatedCommentSerializer},  # ✅ Fixed pagination doc
        description="List comments for a post (if post_id provided) or comments by the authenticated user.",
    )
    def get(self, request, post_id=None):
        if post_id:
            # Get comments for a specific post
            post = get_object_or_404(Post, id=post_id, is_deleted=False)
            logger.debug(f"Post privacy: {post.privacy}")
            if post.privacy == "public":
                # kahit sino puwedeng makakita ng comments
                pass

            elif post.privacy == "followers" and not settings.DEBUG:
                # i-check kung follower si request.user ng post.user
                if (
                    not post.user.followers.filter(id=request.user.id).exists()
                    and request.user != post.user
                ):
                    return Response(
                        {"error": "Only followers can view comments for this post"},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            elif post.privacy == "secret":
                # user lang puwedeng makakita ng comments
                if request.user != post.user:
                    return Response(
                        {
                            "error": "You do not have permission to view comments for this post"
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

            include_replies = (
                request.query_params.get("include_replies", "true").lower() == "true"
            )
            include_deleted = (
                request.query_params.get("include_deleted", "false").lower() == "true"
            )
            comments = CommentService.get_post_comments(
                post=post,
                include_replies=include_replies,
                include_deleted=include_deleted,
            )
        else:
            # Get all comments by the authenticated user
            if not request.user.is_authenticated:
                return Response(
                    {"error": "Authentication required"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            comments = CommentService.get_user_comments(user=request.user)

        # Apply pagination
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(comments, request)
        serializer = CommentDisplaySerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Comment's"],
        request=CommentCreateSerializer,
        responses={201: CommentDisplaySerializer},
        examples=[
            OpenApiExample(
                "Create comment",
                value={
                    "user_id": 1,
                    "post_id": 10,
                    "content": "Great post!",
                    "parent_comment_id": None,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create reply",
                value={
                    "user_id": 1,
                    "post_id": 10,
                    "content": "I agree!",
                    "parent_comment_id": 5,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Comment response",
                value={
                    "id": 123,
                    "post": 10,
                    "user": {
                        "id": 1,
                        "username": "darius",
                        "profile_pic": "https://example.com/avatar.jpg",
                    },
                    "content": "Great post!",
                    "parent_comment": None,
                    "created_at": "2025-03-07T12:34:56Z",
                    "like_count": 3,
                    "has_liked": True,
                    "replies": [],
                },
                response_only=True,
            ),
        ],
        description="Create a new comment on a post.",
    )
    @transaction.atomic
    def post(self, request):
        post_id = request.data.get("post_id", None)
        """Create a new comment on a post"""
        logger.debug(f"Incoming post: {request.data}")
        post = get_object_or_404(Post, id=post_id, is_deleted=False)

        # Check if post is public or user is user
        # logger.debug(f"Post data: {PostSerializer(post).data}")
        # logger.debug(f"Post privacy: {post.privacy}")
        if post.privacy == "public":
            # kahit sino (authenticated user) puwedeng mag-comment
            pass

        elif post.privacy == "followers" and not settings.DEBUG:
            # i-check kung follower si request.user ng post.user
            if not post.user.followers.filter(id=request.user.id).exists():
                return Response(
                    {"error": "Only followers can comment on this post"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        elif post.privacy == "secret":
            # i-check kung user lang ang puwedeng mag-comment
            if post.user != request.user:
                return Response(
                    {"error": "You do not have permission to comment on this post"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Add post_id and user_id to request data
        data = request.data.copy()
        data["post_id"] = post_id
        data["user_id"] = request.user.id

        serializer = CommentCreateSerializer(data=data, context={"request": request})

        if serializer.is_valid(raise_exception=True):
            comment = serializer.save()
            return Response(
                CommentDisplaySerializer(comment, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentDetailView(APIView):
    """View for retrieving, updating, and deleting a specific comment"""

    def get_permissions(self):
        """Set permissions based on request method"""
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_object(self, comment_id):
        """Get comment object or return 404"""
        return get_object_or_404(Comment, id=comment_id)

    @extend_schema(
        tags=["Comment's"],
        responses={200: CommentDisplaySerializer},
        description="Retrieve a single comment by ID.",
    )
    def get(self, request, comment_id):
        """Retrieve a specific comment"""
        comment = self.get_object(comment_id)

        # Check if associated post is accessible
        if not comment.post.privacy == "public" and request.user != comment.post.user:
            return Response(
                {"error": "You do not have permission to view this comment"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CommentDisplaySerializer(comment, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["Comment's"],
        request=CommentCreateSerializer,
        responses={200: CommentDisplaySerializer},
        examples=[
            OpenApiExample(
                "Update comment",
                value={"content": "Updated comment text"},
                request_only=True,
            )
        ],
        description="Update a comment (full or partial).",
    )
    @transaction.atomic
    def put(self, request, comment_id):
        """Update a comment"""
        comment = self.get_object(comment_id)

        # Check ownership
        if request.user != comment.user:
            return Response(
                {"error": "You do not have permission to update this comment"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if post is deleted
        if comment.post.is_deleted:
            return Response(
                {"error": "Cannot update comment on a deleted post"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CommentCreateSerializer(
            comment, data=request.data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            # Ensure user_id and post_id don't change
            if "user_id" in request.data and request.data["user_id"] != comment.user.id:
                return Response(
                    {"error": "Cannot change comment user"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if "post_id" in request.data and request.data["post_id"] != comment.post.id:
                return Response(
                    {"error": "Cannot change comment post"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            updated_comment = serializer.save()
            return Response(
                CommentDisplaySerializer(
                    updated_comment, context={"request": request}
                ).data
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["Comment's"],
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        description="Delete a comment (soft delete).",
    )
    @transaction.atomic
    def delete(self, request, comment_id):
        """Delete a comment"""
        comment = self.get_object(comment_id)

        # Check ownership or if user owns the post
        can_delete = request.user == comment.user or request.user == comment.post.user

        if not can_delete:
            return Response(
                {"error": "You do not have permission to delete this comment"},
                status=status.HTTP_403_FORBIDDEN,
            )

        success = CommentService.delete_comment(comment)
        if success:
            return Response({"message": "Comment deleted successfully"})

        return Response(
            {"error": "Failed to delete comment"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class CommentRepliesView(APIView):
    """View for managing comment replies"""

    def get_permissions(self):
        """Set permissions based on request method"""
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["Comment's"],
        parameters=[
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
        responses={200: PaginatedCommentSerializer},  # ✅ Fixed pagination doc
        description="Get all replies to a specific comment.",
    )
    def get(self, request, comment_id):
        comment = get_object_or_404(Comment, id=comment_id)
        if not comment.post.privacy == "public" and request.user != comment.post.user:
            return Response(
                {
                    "error": "You do not have permission to view replies for this comment"
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        replies = CommentService.get_comment_replies(comment=comment)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(replies, request)
        serializer = CommentDisplaySerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Comment's"],
        request=CommentCreateSerializer,
        responses={201: CommentDisplaySerializer},
        examples=[
            OpenApiExample(
                "Create reply", value={"content": "This is a reply"}, request_only=True
            )
        ],
        description="Create a reply to an existing comment.",
    )
    @transaction.atomic
    def post(self, request, comment_id):
        """Create a reply to a comment"""
        parent_comment = get_object_or_404(Comment, id=comment_id)

        # Check if parent comment's post is accessible
        if (
            not parent_comment.post.privacy == "public"
            and request.user != parent_comment.post.user
        ):
            return Response(
                {"error": "You do not have permission to reply to this comment"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if post is deleted
        if parent_comment.post.is_deleted:
            return Response(
                {"error": "Cannot reply to comment on a deleted post"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Add parent_comment_id and user_id to request data
        data = request.data.copy()
        data["post_id"] = parent_comment.post.id
        data["user_id"] = request.user.id
        data["parent_comment_id"] = comment_id

        serializer = CommentDisplaySerializer(data=data, context={"request": request})

        if serializer.is_valid():
            comment = serializer.save()
            return Response(
                CommentDisplaySerializer(comment, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentThreadView(APIView):
    """View for getting full comment thread"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Comment's"],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "comment_id": {"type": "integer"},
                    "post_id": {"type": "integer"},
                    "thread": CommentDisplaySerializer(many=True).data,
                },
            }
        },
        description="Get the full thread (ancestors and all descendants) of a comment.",
    )
    def get(self, request, comment_id):
        """Get full thread for a comment (parent and all children)"""
        comment = get_object_or_404(Comment, id=comment_id)

        # Check if associated post is accessible
        if not comment.post.privacy == "public" and request.user != comment.post.user:
            return Response(
                {"error": "You do not have permission to view this thread"},
                status=status.HTTP_403_FORBIDDEN,
            )

        thread = CommentService.get_comment_thread(comment)
        serializer = CommentDisplaySerializer(
            thread, many=True, context={"request": request}
        )

        return Response(
            {
                "comment_id": comment_id,
                "post_id": comment.post.id,
                "thread": serializer.data,
            }
        )


class CommentSearchView(APIView):
    """View for searching comments"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Comment's"],
        parameters=[
            OpenApiParameter(
                name="query", type=str, description="Search term", required=True
            ),
            OpenApiParameter(
                name="user_id",
                type=int,
                description="Filter by user ID",
                required=False,
            ),
            OpenApiParameter(
                name="post_id",
                type=int,
                description="Filter by post ID",
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
        responses={200: PaginatedCommentSerializer},  # ✅ Fixed pagination doc
        description="Search comments by content.",
    )
    def get(self, request):
        query = request.query_params.get("query", "")
        user_id = request.query_params.get("user_id")
        post_id = request.query_params.get("post_id")
        if not query:
            return Response(
                {"error": "Query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = None
        if user_id:
            from users.models import User

            user = get_object_or_404(User, id=user_id)
        post = None
        if post_id:
            post = get_object_or_404(Post, id=post_id, is_deleted=False)
            if not post.privacy == "public" and request.user != post.user:
                return Response(
                    {
                        "error": "You do not have permission to search comments on this post"
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        comments = CommentService.search_comments(query=query, user=user, post=post)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(comments, request)
        serializer = CommentDisplaySerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)
