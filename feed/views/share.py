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


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class PaginatedShareFeedSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ShareFeedSerializer(many=True)


class ShareListResponseData(serializers.Serializer):
    pagination = PaginatedShareFeedSerializer()


class ShareListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ShareListResponseData(allow_null=True)


class ShareCreateResponseData(serializers.Serializer):
    share = ShareDisplaySerializer()


class ShareCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ShareCreateResponseData(allow_null=True)


class ShareDetailResponseData(serializers.Serializer):
    share = ShareDisplaySerializer()


class ShareDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ShareDetailResponseData(allow_null=True)


class ShareUpdateResponseData(serializers.Serializer):
    share = ShareDisplaySerializer()


class ShareUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ShareUpdateResponseData(allow_null=True)


class ShareDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class ShareObjectSharesResponseData(serializers.Serializer):
    pagination = PaginatedShareFeedSerializer()


class ShareObjectSharesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ShareObjectSharesResponseData(allow_null=True)


class UserShareStatisticsResponseData(serializers.Serializer):
    total_shares = serializers.IntegerField()
    type_breakdown = serializers.ListField(child=serializers.DictField())
    first_share_date = serializers.DateTimeField(allow_null=True)


class UserShareStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserShareStatisticsResponseData()


class ShareRestoreResponseData(serializers.Serializer):
    share = ShareDisplaySerializer()


class ShareRestoreResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ShareRestoreResponseData(allow_null=True)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_shares(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedShareFeedSerializer.
    """
    serializer = ShareFeedSerializer(page, many=True, context={'request': request})
    data = {
        'page': paginator.page.number,
        'hasNext': paginator.page.has_next(),
        'hasPrev': paginator.page.has_previous(),
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class ShareListView(APIView):
    """List shares (optionally filtered by user or content object) and create a new share."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["Share Post's"],
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
        responses={200: ShareListResponseSerializer},
        description="List shares, optionally filtered by user or content object.",
    )
    def get(self, request):
        try:
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
                        {
                            "status": False,
                            "message": "Invalid content_type format",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            shares = shares.order_by("-created_at")

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(shares, request)
            paginated_data = wrap_paginated_shares(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Shares retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error listing shares")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Share Post's"],
        request=ShareCreateSerializer,
        responses={201: ShareCreateResponseSerializer},
        description="Create a new share.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = ShareCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid(raise_exception=True):
            share = serializer.save()
            data = ShareDisplaySerializer(share, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Share successful",
                    "data": {"share": data},
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {
                "status": False,
                "message": "Failed to share posts",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


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
        tags=["Share Post's"],
        responses={200: ShareDetailResponseSerializer},
        description="Retrieve a single share by ID.",
    )
    def get(self, request, share_id):
        try:
            share = self.get_object(share_id)
            if not share:
                return Response(
                    {
                        "status": False,
                        "message": "Share not found or deleted.",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            data = ShareDisplaySerializer(share, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Share retrieved.",
                    "data": {"share": data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving share %s", share_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Share Post's"],
        request=ShareCreateSerializer,  # reuse create serializer for updates
        responses={200: ShareUpdateResponseSerializer},
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
        try:
            share = self.get_object(share_id)
            if not share:
                return Response(
                    {
                        "status": False,
                        "message": "Share not found or deleted.",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Ownership check
            if request.user != share.user:
                return Response(
                    {
                        "status": False,
                        "message": "You do not have permission to update this share.",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Partial update: allow only caption and privacy
            caption = request.data.get("caption", share.caption)
            privacy = request.data.get("privacy", share.privacy)

            updated_share = ShareService.update_share(
                share=share,
                caption=caption,
                privacy=privacy,
            )
            data = ShareDisplaySerializer(updated_share, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Share updated successfully.",
                    "data": {"share": data},
                }
            )
        except ValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error updating share %s", share_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Share Post's"],
        parameters=[
            OpenApiParameter(
                name="hard",
                type=bool,
                description="Permanently delete instead of soft delete",
                required=False,
            ),
        ],
        responses={200: ShareDeleteResponseSerializer},
        description="Delete a share (soft delete by default).",
    )
    @transaction.atomic
    def delete(self, request, share_id):
        try:
            share = self.get_object(share_id)
            if not share:
                return Response(
                    {
                        "status": False,
                        "message": "Share not found.",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if request.user != share.user:
                return Response(
                    {
                        "status": False,
                        "message": "You do not have permission to delete this share.",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            hard_delete = request.query_params.get("hard", "false").lower() == "true"
            success = ShareService.delete_share(share, soft=not hard_delete)

            if success:
                message = "Share deleted successfully"
                if hard_delete:
                    message = "Share permanently deleted"
                return Response(
                    {
                        "status": True,
                        "message": message,
                        "data": None,
                    }
                )
            return Response(
                {
                    "status": False,
                    "message": "Failed to delete share.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.exception("Error deleting share %s", share_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ShareObjectSharesView(APIView):
    """Get all shares of a specific content object."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Share Post's"],
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
        responses={200: ShareObjectSharesResponseSerializer},
        description="Get all shares of a specific content object.",
    )
    def get(self, request):
        content_type_str = request.query_params.get("content_type")
        object_id = request.query_params.get("object_id")

        if not content_type_str or not object_id:
            return Response(
                {
                    "status": False,
                    "message": "Both content_type and object_id are required.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            app_label, model = content_type_str.split(".")
            content_type = ContentType.objects.get(app_label=app_label, model=model)
        except (ValueError, ContentType.DoesNotExist):
            return Response(
                {
                    "status": False,
                    "message": "Invalid content_type.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            shares = (
                Share.objects.filter(
                    content_type=content_type, object_id=object_id, is_deleted=False
                )
                .select_related("user")
                .order_by("-created_at")
            )

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(shares, request)
            paginated_data = wrap_paginated_shares(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Shares retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving shares for object")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ShareUserStatisticsView(APIView):
    """Get share statistics for a user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Share Post's"],
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (defaults to current user)",
                required=False,
            ),
        ],
        responses={200: UserShareStatisticsResponseSerializer},
        description="Get share statistics for a user.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                target_user = get_object_or_404(User, id=user_id)
            else:
                target_user = request.user

            stats = ShareService.get_user_share_statistics(target_user)
            return Response(
                {
                    "status": True,
                    "message": "User statistics retrieved.",
                    "data": stats,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user share statistics")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ShareRestoreView(APIView):
    """Restore a soft-deleted share."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Share Post's"],
        responses={
            200: ShareRestoreResponseSerializer,
            403: ShareRestoreResponseSerializer,
            400: ShareRestoreResponseSerializer,
        },
        description="Restore a soft-deleted share (only owner).",
    )
    @transaction.atomic
    def post(self, request, share_id):
        try:
            share = get_object_or_404(Share, id=share_id)

            if request.user != share.user:
                return Response(
                    {
                        "status": False,
                        "message": "You do not have permission to restore this share.",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            success = ShareService.restore_share(share)
            if success:
                data = ShareDisplaySerializer(share, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Share restored successfully.",
                        "data": {"share": data},
                    },
                    status=status.HTTP_200_OK,
                )

            return Response(
                {
                    "status": False,
                    "message": "Share is not deleted or could not be restored.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error restoring share %s", share_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )