import logging

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import serializers
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
    inline_serializer,
)

from feed.models import Share
from feed.serializers.share import (
    ShareMinimalSerializer,
    ShareCreateSerializer,
    ShareDisplaySerializer,
    ShareFeedSerializer,
)
from feed.services.share import ShareService
from global_utils.pagination import StandardResultsSetPagination
from users.models import User

logger = logging.getLogger(__name__)


# ----- Paginated response serializer for drf-spectacular -----
class PaginatedShareFeedSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ShareFeedSerializer(many=True)


# --------------------------------------------------------------


class ShareListView(APIView):
    """List shares (optionally filtered by user or content object) and create a new share."""

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
                name="content_type",
                type=str,
                description="Filter by content type (e.g., 'feed.post')",
                required=False,
            ),
            OpenApiParameter(
                name="object_id",
                type=int,
                description="Filter by object ID (requires content_type)",
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
        responses={200: PaginatedShareFeedSerializer},
        description="List shares, optionally filtered by user or content object.",
    )
    def get(self, request):
        user_id = request.query_params.get("user_id")
        content_type_str = request.query_params.get("content_type")
        object_id = request.query_params.get("object_id")

        shares = Share.objects.filter(is_deleted=False).select_related("user")

        if user_id:
            shares = shares.filter(user_id=user_id)

        if content_type_str and object_id:
            try:
                app_label, model = content_type_str.split(".")
                content_type = ContentType.objects.get(app_label=app_label, model=model)
                shares = shares.filter(content_type=content_type, object_id=object_id)
            except (ValueError, ContentType.DoesNotExist):
                return Response(
                    {"error": "Invalid content_type format"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        shares = shares.order_by("-created_at")

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(shares, request)
        serializer = ShareFeedSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=ShareCreateSerializer,
        responses={201: ShareDisplaySerializer},
        examples=[
            OpenApiExample(
                "Share a post",
                value={
                    "content_type": "feed.post",
                    "object_id": 123,
                    "caption": "Check this out!",
                    "privacy": "public",
                },
                request_only=True,
            ),
        ],
        description="Create a new share.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = ShareCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid(raise_exception=True):
            share = serializer.save()
            return Response(
                ShareDisplaySerializer(share, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ShareDetailView(APIView):
    """Retrieve, update, or delete a specific share."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_object(self, share_id):
        try:
            return Share.objects.get(id=share_id, is_deleted=False)
        except Share.DoesNotExist:
            return None

    @extend_schema(
        responses={200: ShareDisplaySerializer},
        description="Retrieve a single share by ID.",
    )
    def get(self, request, share_id):
        share = self.get_object(share_id)
        if not share:
            return Response(
                {"error": "Share not found or deleted."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = ShareDisplaySerializer(share, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=ShareCreateSerializer,  # reuse create serializer for updates
        responses={200: ShareDisplaySerializer},
        examples=[
            OpenApiExample(
                "Update share",
                value={"caption": "Updated caption", "privacy": "followers"},
                request_only=True,
            ),
        ],
        description="Update a share (partial update allowed).",
    )
    @transaction.atomic
    def put(self, request, share_id):
        share = self.get_object(share_id)
        if not share:
            return Response(
                {"error": "Share not found or deleted."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Ownership check
        if request.user != share.user:
            return Response(
                {"error": "You do not have permission to update this share."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Partial update: allow only caption and privacy
        caption = request.data.get("caption", share.caption)
        privacy = request.data.get("privacy", share.privacy)

        try:
            updated_share = ShareService.update_share(
                share=share,
                caption=caption,
                privacy=privacy,
            )
            serializer = ShareDisplaySerializer(
                updated_share, context={"request": request}
            )
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
        description="Delete a share (soft delete by default).",
    )
    @transaction.atomic
    def delete(self, request, share_id):
        share = self.get_object(share_id)
        if not share:
            return Response(
                {"error": "Share not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user != share.user:
            return Response(
                {"error": "You do not have permission to delete this share."},
                status=status.HTTP_403_FORBIDDEN,
            )

        hard_delete = request.query_params.get("hard", "false").lower() == "true"
        success = ShareService.delete_share(share, soft=not hard_delete)

        if success:
            message = "Share deleted successfully"
            if hard_delete:
                message = "Share permanently deleted"
            return Response({"message": message})
        return Response(
            {"error": "Failed to delete share."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ShareObjectSharesView(APIView):
    """Get all shares of a specific content object."""

    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Content type (e.g., 'feed.post')",
                required=True,
            ),
            OpenApiParameter(
                name="object_id",
                type=int,
                description="Object ID",
                required=True,
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
        responses={200: PaginatedShareFeedSerializer},
        description="Get all shares of a specific content object.",
    )
    def get(self, request):
        content_type_str = request.query_params.get("content_type")
        object_id = request.query_params.get("object_id")

        if not content_type_str or not object_id:
            return Response(
                {"error": "Both content_type and object_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            app_label, model = content_type_str.split(".")
            content_type = ContentType.objects.get(app_label=app_label, model=model)
        except (ValueError, ContentType.DoesNotExist):
            return Response(
                {"error": "Invalid content_type."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shares = (
            Share.objects.filter(
                content_type=content_type, object_id=object_id, is_deleted=False
            )
            .select_related("user")
            .order_by("-created_at")
        )

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(shares, request)
        serializer = ShareFeedSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class UserShareStatisticsSerializer(serializers.Serializer):
    total_shares = serializers.IntegerField(read_only=True)
    type_breakdown = serializers.ListField(
        child=serializers.DictField(), read_only=True
    )
    first_share_date = serializers.DateTimeField(read_only=True, allow_null=True)


class ShareUserStatisticsView(APIView):
    """Get share statistics for a user."""

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
        responses={200: UserShareStatisticsSerializer},
        description="Get share statistics for a user.",
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
        else:
            target_user = request.user

        stats = ShareService.get_user_share_statistics(target_user)
        return Response(stats)


class ShareRestoreResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    share = ShareDisplaySerializer()


class ShareRestoreView(APIView):
    """Restore a soft-deleted share."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: ShareRestoreResponseSerializer},
        description="Restore a soft-deleted share (only owner).",
    )
    @transaction.atomic
    def post(self, request, share_id):
        share = get_object_or_404(Share, id=share_id)

        if request.user != share.user:
            return Response(
                {"error": "You do not have permission to restore this share."},
                status=status.HTTP_403_FORBIDDEN,
            )

        success = ShareService.restore_share(share)
        if success:
            return Response(
                {
                    "message": "Share restored successfully.",
                    "share": ShareDisplaySerializer(
                        share, context={"request": request}
                    ).data,
                }
            )
        return Response(
            {"error": "Share is not deleted or could not be restored."},
            status=status.HTTP_400_BAD_REQUEST,
        )
