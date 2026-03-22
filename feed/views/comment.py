# feed/views/comment_views.py

import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from feed.models import Comment, Post
from feed.serializers.comment import CommentCreateSerializer, CommentDisplaySerializer
from feed.services import CommentService
from feed.utils.comment import can_view_comments, get_content_object
from global_utils.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


# ---------------------------- Paginated Response Serializer ----------------------------
class PaginatedCommentSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = CommentDisplaySerializer(many=True)


# ---------------------------- Views ----------------------------
class MyCommentListView(APIView):
    """List comments created by the authenticated user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Comment's"],
        parameters=[
            OpenApiParameter(name="include_deleted", type=bool, required=False),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: PaginatedCommentSerializer},
        description="List of comments by the authenticated user.",
    )
    def get(self, request):
        include_deleted = (
            request.query_params.get("include_deleted", "false").lower() == "true"
        )
        comments = CommentService.get_user_comments(
            user=request.user, include_deleted=include_deleted
        )
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
        description="Create a new comment on any content object.",
    )
    @transaction.atomic
    def post(self, request):
        """
        Create a comment. The request must contain `content_type` (e.g., 'post')
        and `object_id` to identify the target object.
        """
        serializer = CommentCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid(raise_exception=True):
            comment = serializer.save()
            return Response(
                CommentDisplaySerializer(comment, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentListView(APIView):
    """
    List comments on any content object using query parameters:
    ?content_type=<model_name>&object_id=<id>
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def _get_target_object(self, request):
        """Retrieve target object from query parameters."""
        content_type_name = request.query_params.get("content_type")
        object_id = request.query_params.get("object_id")
        if not content_type_name or not object_id:
            return None
        obj = get_content_object(content_type_name, object_id)
        if obj is None:
            return None
        # Optional: check if the object is deleted if it has an is_deleted flag
        if hasattr(obj, "is_deleted") and obj.is_deleted:
            return None
        return obj

    @extend_schema(
        tags=["Comment's"],
        parameters=[
            OpenApiParameter(
                name="content_type",
                type=str,
                description="e.g., 'post', 'reel'",
                required=True,
            ),
            OpenApiParameter(
                name="object_id",
                type=int,
                description="ID of the target object",
                required=True,
            ),
            OpenApiParameter(
                name="include_replies", type=bool, default=True, required=False
            ),
            OpenApiParameter(
                name="include_deleted", type=bool, default=False, required=False
            ),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: PaginatedCommentSerializer},
        description="List comments for a content object. Must provide content_type and object_id.",
    )
    def get(self, request):
        target_obj = self._get_target_object(request)
        if target_obj is None:
            return Response(
                {
                    "error": "Target object not found or not accessible. "
                    "Please provide valid content_type and object_id."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not can_view_comments(request.user, target_obj):
            return Response(
                {
                    "error": "You do not have permission to view comments on this object."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        include_replies = (
            request.query_params.get("include_replies", "true").lower() == "true"
        )
        include_deleted = (
            request.query_params.get("include_deleted", "false").lower() == "true"
        )

        comments = CommentService.get_comments_for_object(
            content_object=target_obj,
            include_replies=include_replies,
            include_deleted=include_deleted,
        )

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(comments, request)
        serializer = CommentDisplaySerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)


class CommentDetailView(APIView):
    """Retrieve, update, or delete a specific comment."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_object(self, comment_id):
        return get_object_or_404(Comment, id=comment_id)

    @extend_schema(
        tags=["Comment's"],
        responses={200: CommentDisplaySerializer},
        description="Retrieve a single comment by ID.",
    )
    def get(self, request, comment_id):
        comment = self.get_object(comment_id)

        # Permission: can view the target object's comments?
        if not can_view_comments(request.user, comment.content_object):
            return Response(
                {"error": "You do not have permission to view this comment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CommentDisplaySerializer(comment, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["Comment's"],
        request=CommentCreateSerializer,
        responses={200: CommentDisplaySerializer},
        description="Update a comment (full or partial).",
    )
    @transaction.atomic
    def put(self, request, comment_id):
        comment = self.get_object(comment_id)

        # Check ownership
        if request.user != comment.user:
            return Response(
                {"error": "You do not have permission to update this comment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if the target object is still available (not deleted)
        if (
            hasattr(comment.content_object, "is_deleted")
            and comment.content_object.is_deleted
        ):
            return Response(
                {"error": "Cannot update comment on a deleted object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CommentCreateSerializer(
            comment, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
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
        description="Soft delete a comment.",
    )
    @transaction.atomic
    def delete(self, request, comment_id):
        comment = self.get_object(comment_id)

        # Permission: owner of comment or owner of the target object
        can_delete = (request.user == comment.user) or (
            hasattr(comment.content_object, "user")
            and request.user == comment.content_object.user
        )

        if not can_delete:
            return Response(
                {"error": "You do not have permission to delete this comment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        success = CommentService.delete_comment(comment)
        if success:
            return Response({"message": "Comment deleted successfully."})
        return Response(
            {"error": "Failed to delete comment."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class CommentRepliesView(APIView):
    """List replies to a comment, and create a reply."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["Comment's"],
        parameters=[
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: PaginatedCommentSerializer},
        description="Get all replies to a specific comment.",
    )
    def get(self, request, comment_id):
        comment = get_object_or_404(Comment, id=comment_id)

        if not can_view_comments(request.user, comment.content_object):
            return Response(
                {"error": "You do not have permission to view replies."},
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
        description="Create a reply to an existing comment.",
    )
    @transaction.atomic
    def post(self, request, comment_id):
        parent_comment = get_object_or_404(Comment, id=comment_id)

        if not can_view_comments(request.user, parent_comment.content_object):
            return Response(
                {"error": "You do not have permission to reply to this comment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if (
            hasattr(parent_comment.content_object, "is_deleted")
            and parent_comment.content_object.is_deleted
        ):
            return Response(
                {"error": "Cannot reply to a comment on a deleted object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # The serializer expects content_type/object_id or post_id; we'll reuse the create serializer.
        data = request.data.copy()
        data["target_type"] = parent_comment.content_type.model
        data["target_id"] = parent_comment.object_id
        data["parent_comment_id"] = comment_id

        serializer = CommentCreateSerializer(data=data, context={"request": request})
        if serializer.is_valid():
            comment = serializer.save()
            return Response(
                CommentDisplaySerializer(comment, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class CommentSearchView(APIView):
    """Search comments by content."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Comment's"],
        parameters=[
            OpenApiParameter(name="query", type=str, required=True),
            OpenApiParameter(name="user_id", type=int, required=False),
            OpenApiParameter(name="content_type", type=str, required=False),
            OpenApiParameter(name="object_id", type=int, required=False),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: PaginatedCommentSerializer},
        description="Search comments by content, optionally filtered by user or target object.",
    )
    def get(self, request):
        query = request.query_params.get("query", "").strip()
        if not query:
            return Response(
                {"error": "Query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = None
        user_id = request.query_params.get("user_id")
        if user_id:
            from users.models import User

            user = get_object_or_404(User, id=user_id)

        content_object = None
        content_type_name = request.query_params.get("content_type")
        object_id = request.query_params.get("object_id")
        if content_type_name and object_id:
            content_object = get_content_object(content_type_name, object_id)
            if content_object is None or (
                hasattr(content_object, "is_deleted") and content_object.is_deleted
            ):
                return Response(
                    {"error": "Target object not found or not accessible."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not can_view_comments(request.user, content_object):
                return Response(
                    {
                        "error": "You do not have permission to search comments on this object."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        comments = CommentService.search_comments(
            query=query, user=user, content_object=content_object
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(comments, request)
        serializer = CommentDisplaySerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)
