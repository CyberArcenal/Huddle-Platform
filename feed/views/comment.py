# feed/views/comment_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from feed.models import Comment, Post
from feed.serializers.comment import CommentSerializer
from feed.services import CommentService
from global_utils.pagination import StandardResultsSetPagination


class CommentListView(APIView):
    """View for listing and creating comments"""

    def get_permissions(self):
        """Set permissions based on request method"""
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='post_id', type=int, description='ID of the post to get comments for', required=False, location=OpenApiParameter.PATH),
            OpenApiParameter(name='include_replies', type=bool, description='Include nested replies', required=False),
            OpenApiParameter(name='include_deleted', type=bool, description='Include soft-deleted comments (admin only)', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: CommentSerializer(many=True)},
        description="List comments for a post (if post_id provided) or comments by the authenticated user."
    )
    def get(self, request, post_id=None):
        if post_id:
            # Get comments for a specific post
            post = get_object_or_404(Post, id=post_id, is_deleted=False)
            if not post.is_public and request.user != post.user:
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
        serializer = CommentSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=CommentSerializer,
        responses={201: CommentSerializer},
        examples=[
            OpenApiExample(
                'Create comment',
                value={
                    'content': 'Great post!',
                    'parent_comment_id': None
                },
                request_only=True
            ),
            OpenApiExample(
                'Create reply',
                value={
                    'content': 'I agree!',
                    'parent_comment_id': 5
                },
                request_only=True
            ),
            OpenApiExample(
                'Comment response',
                value={
                    'id': 123,
                    'post': 1,
                    'user': 1,
                    'content': 'Great post!',
                    'parent_comment': None,
                    'created_at': '2025-03-07T12:34:56Z',
                    'is_deleted': False
                },
                response_only=True
            )
        ],
        description="Create a new comment on a post."
    )
    def post(self, request, post_id):
        """Create a new comment on a post"""
        post = get_object_or_404(Post, id=post_id, is_deleted=False)

        # Check if post is public or user is owner
        if not post.is_public and request.user != post.user:
            return Response(
                {"error": "You do not have permission to comment on this post"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Add post_id and user_id to request data
        data = request.data.copy()
        data["post_id"] = post_id
        data["user_id"] = request.user.id

        serializer = CommentSerializer(data=data, context={"request": request})

        if serializer.is_valid():
            comment = serializer.save()
            return Response(
                CommentSerializer(comment, context={"request": request}).data,
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
        responses={200: CommentSerializer},
        description="Retrieve a single comment by ID."
    )
    def get(self, request, comment_id):
        """Retrieve a specific comment"""
        comment = self.get_object(comment_id)

        # Check if associated post is accessible
        if not comment.post.is_public and request.user != comment.post.user:
            return Response(
                {"error": "You do not have permission to view this comment"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CommentSerializer(comment, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=CommentSerializer,
        responses={200: CommentSerializer},
        examples=[
            OpenApiExample(
                'Update comment',
                value={'content': 'Updated comment text'},
                request_only=True
            )
        ],
        description="Update a comment (full or partial)."
    )
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

        serializer = CommentSerializer(
            comment, data=request.data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            # Ensure user_id and post_id don't change
            if "user_id" in request.data and request.data["user_id"] != comment.user.id:
                return Response(
                    {"error": "Cannot change comment owner"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if "post_id" in request.data and request.data["post_id"] != comment.post.id:
                return Response(
                    {"error": "Cannot change comment post"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            updated_comment = serializer.save()
            return Response(
                CommentSerializer(updated_comment, context={"request": request}).data
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}},
        description="Delete a comment (soft delete)."
    )
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
        parameters=[
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: CommentSerializer(many=True)},
        description="Get all replies to a specific comment."
    )
    def get(self, request, comment_id):
        comment = get_object_or_404(Comment, id=comment_id)
        if not comment.post.is_public and request.user != comment.post.user:
            return Response(
                {
                    "error": "You do not have permission to view replies for this comment"
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        replies = CommentService.get_comment_replies(comment=comment)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(replies, request)
        serializer = CommentSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=CommentSerializer,
        responses={201: CommentSerializer},
        examples=[
            OpenApiExample(
                'Create reply',
                value={'content': 'This is a reply'},
                request_only=True
            )
        ],
        description="Create a reply to an existing comment."
    )
    def post(self, request, comment_id):
        """Create a reply to a comment"""
        parent_comment = get_object_or_404(Comment, id=comment_id)

        # Check if parent comment's post is accessible
        if (
            not parent_comment.post.is_public
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

        serializer = CommentSerializer(data=data, context={"request": request})

        if serializer.is_valid():
            comment = serializer.save()
            return Response(
                CommentSerializer(comment, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentThreadView(APIView):
    """View for getting full comment thread"""

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: {'type': 'object', 'properties': {
            'comment_id': {'type': 'integer'},
            'post_id': {'type': 'integer'},
            'thread': CommentSerializer(many=True).data
        }}},
        description="Get the full thread (ancestors and all descendants) of a comment."
    )
    def get(self, request, comment_id):
        """Get full thread for a comment (parent and all children)"""
        comment = get_object_or_404(Comment, id=comment_id)

        # Check if associated post is accessible
        if not comment.post.is_public and request.user != comment.post.user:
            return Response(
                {"error": "You do not have permission to view this thread"},
                status=status.HTTP_403_FORBIDDEN,
            )

        thread = CommentService.get_comment_thread(comment)
        serializer = CommentSerializer(thread, many=True, context={"request": request})

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
        parameters=[
            OpenApiParameter(name='query', type=str, description='Search term', required=True),
            OpenApiParameter(name='user_id', type=int, description='Filter by user ID', required=False),
            OpenApiParameter(name='post_id', type=int, description='Filter by post ID', required=False),
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: CommentSerializer(many=True)},
        description="Search comments by content."
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
            if not post.is_public and request.user != post.user:
                return Response(
                    {
                        "error": "You do not have permission to search comments on this post"
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        comments = CommentService.search_comments(
            query=query, user=user, post=post
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(comments, request)
        serializer = CommentSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)