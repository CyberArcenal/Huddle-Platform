import logging

from rest_framework.views import APIView, PermissionDenied
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, OpenApiParameter

from feed.models.bookmark import ObjectBookmark
from feed.services.bookmark import BookmarkService
from feed.serializers.book_mark import (
    BookmarkDisplaySerializer,
    BookmarkMinimalSerializer,
    BookmarkCreateSerializer,
    BookmarkStatisticsSerializer,
)
from django.db import transaction
from global_utils.pagination import AnalyticsPagination

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Input serializers
# ----------------------------------------------------------------------
class BookmarkActionSerializer(serializers.Serializer):
    target_type = serializers.CharField(
        help_text="Model name (e.g., 'post', 'comment')"
    )
    target_id = serializers.IntegerField(help_text="Object ID")


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class PaginatedBookmarkMinimalSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = BookmarkMinimalSerializer(many=True)


class BookmarkListResponseData(serializers.Serializer):
    pagination = PaginatedBookmarkMinimalSerializer()


class BookmarkListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = BookmarkListResponseData(allow_null=True)


class BookmarkCreateResponseData(serializers.Serializer):
    bookmark = BookmarkDisplaySerializer()


class BookmarkCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = BookmarkCreateResponseData(allow_null=True)


class BookmarkDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class BookmarkStatisticsResponseData(serializers.Serializer):
    bookmark_count = serializers.IntegerField()
    has_bookmarked = serializers.BooleanField()


class BookmarkStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = BookmarkStatisticsResponseData()


class TopBookmarkItemSerializer(serializers.Serializer):
    content_type = serializers.CharField()
    object_id = serializers.IntegerField()
    bookmark_count = serializers.IntegerField()


class BookmarkTopResponseData(serializers.Serializer):
    results = TopBookmarkItemSerializer(many=True)
    limit = serializers.IntegerField()


class BookmarkTopResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = BookmarkTopResponseData()


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_bookmarks(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedBookmarkMinimalSerializer.
    """
    serializer = BookmarkMinimalSerializer(page, many=True, context={'request': request})
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

class BookmarkListView(APIView):
    """List all bookmarks for the authenticated user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Bookmarks"],
        parameters=[
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Filter by content type (model name, e.g., 'post')",
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
        responses={200: BookmarkListResponseSerializer},
        description="Get all bookmarks created by the current user.",
    )
    def get(self, request):
        try:
            queryset = (
                ObjectBookmark.objects.filter(user=request.user)
                .select_related("user", "content_type")
                .order_by("-created_at")
            )

            content_type_filter = request.query_params.get("content_type")
            if content_type_filter:
                try:
                    ct = ContentType.objects.get(model=content_type_filter)
                    queryset = queryset.filter(content_type=ct)
                except ContentType.DoesNotExist:
                    return Response(
                        {
                            "status": False,
                            "message": f"Invalid content type: {content_type_filter}",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            paginator = AnalyticsPagination()
            page = paginator.paginate_queryset(queryset, request)
            paginated_data = wrap_paginated_bookmarks(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Bookmarks retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error listing bookmarks")
            return Response(
                {
                    "status": False,
                    "message": "something went wrong",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BookmarkDetailView(APIView):
    """Add or remove a bookmark for a specific object."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Bookmarks"],
        request=BookmarkActionSerializer,
        responses={
            201: BookmarkCreateResponseSerializer,
            400: BookmarkCreateResponseSerializer,
            403: BookmarkCreateResponseSerializer,
            404: BookmarkCreateResponseSerializer,
        },
        description="Create a bookmark for the given object.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = BookmarkActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Invalid request data.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]

        # Resolve ContentType: accept "app_label.model" or just "model"
        try:
            if "." in target_type:
                app_label, model = target_type.split(".", 1)
                ct = ContentType.objects.get(app_label=app_label, model=model)
            else:
                ct = ContentType.objects.get(model=target_type)
        except ContentType.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": f"Invalid content type: {target_type}",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Retrieve the target object
        try:
            obj = ct.get_object_for_this_type(pk=target_id)
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": f"Object with ID {target_id} not found.",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create bookmark via service
        try:
            bookmark = BookmarkService.add_bookmark(user=request.user, obj=obj)
        except PermissionDenied:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to bookmark this object.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Failed to create bookmark.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception(
                "Unexpected error creating bookmark for %s:%s - %s",
                target_type,
                target_id,
                e,
            )
            return Response(
                {
                    "status": False,
                    "message": "An unexpected error occurred.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_data = BookmarkDisplaySerializer(
            bookmark, context={"request": request}
        ).data
        return Response(
            {
                "status": True,
                "message": "Bookmark created successfully.",
                "data": {"bookmark": response_data},
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=["Bookmarks"],
        request=BookmarkActionSerializer,
        responses={
            200: BookmarkDeleteResponseSerializer,
            400: BookmarkDeleteResponseSerializer,
            403: BookmarkDeleteResponseSerializer,
            404: BookmarkDeleteResponseSerializer,
            500: BookmarkDeleteResponseSerializer,
        },
        description="Remove a bookmark for the given object.",
    )
    @transaction.atomic
    def delete(self, request):
        serializer = BookmarkActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Invalid request data.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]

        # Resolve ContentType: accept "app_label.model" or just "model"
        try:
            if "." in target_type:
                app_label, model = target_type.split(".", 1)
                ct = ContentType.objects.get(app_label=app_label, model=model)
            else:
                ct = ContentType.objects.get(model=target_type)
        except ContentType.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": f"Invalid content type: {target_type}",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Try to get the actual object; if not found, proceed to remove bookmarks by content_type + id
        obj = None
        try:
            obj = ct.get_object_for_this_type(pk=target_id)
        except Exception:
            obj = None

        try:
            if obj is not None:
                BookmarkService.remove_bookmark(user=request.user, obj=obj)
            else:
                # Use fallback removal by content_type + object_id
                # The service may or may not have this method; if not, we handle directly.
                try:
                    BookmarkService.remove_bookmark_by_target(
                        user=request.user, content_type=ct, object_id=target_id
                    )
                except AttributeError:
                    # Direct deletion fallback
                    ObjectBookmark.objects.filter(
                        user=request.user, content_type=ct, object_id=target_id
                    ).delete()

            return Response(
                {
                    "status": True,
                    "message": "Bookmark removed successfully.",
                    "data": None,
                },
                status=status.HTTP_200_OK,
            )
        except PermissionDenied:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to remove this bookmark.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception as e:
            logger.exception(
                "Failed to remove bookmark for %s:%s - %s", target_type, target_id, e
            )
            return Response(
                {
                    "status": False,
                    "message": "Failed to remove bookmark.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BookmarkStatisticsView(APIView):
    """Get bookmark count and user status for a given object."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Bookmarks"],
        parameters=[
            OpenApiParameter(
                name="target_type",
                type=str,
                description="Model name (e.g., 'post')",
                required=True,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="target_id",
                type=int,
                description="Object ID",
                required=True,
                location=OpenApiParameter.QUERY,
            ),
        ],
        responses={200: BookmarkStatisticsResponseSerializer},
        description="Get total bookmarks for the object and whether the current user has bookmarked it.",
    )
    def get(self, request):
        target_type = request.query_params.get("target_type")
        target_id = request.query_params.get("target_id")

        if not target_type or not target_id:
            return Response(
                {
                    "status": False,
                    "message": "target_type and target_id are required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ct = ContentType.objects.get(model=target_type)
        except ContentType.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": f"Invalid content type: {target_type}",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Try to get the object; if not found, return zero counts
        try:
            obj = ct.get_object_for_this_type(pk=target_id)
        except Exception:
            obj = None

        if obj is None:
            data = {
                "bookmark_count": 0,
                "has_bookmarked": False,
            }
        else:
            data = {
                "bookmark_count": BookmarkService.get_bookmark_count(obj),
                "has_bookmarked": BookmarkService.has_bookmarked(request.user, obj),
            }

        return Response(
            {
                "status": True,
                "message": "Bookmark statistics retrieved.",
                "data": data,
            }
        )


class BookmarkTopView(APIView):
    """List most bookmarked objects globally (admin only by default)."""

    permission_classes = [IsAdminUser]  # or IsAuthenticated if you want public

    @extend_schema(
        tags=["Bookmarks"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of top objects to return (default 10)",
                required=False,
            ),
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Filter by content type (model name)",
                required=False,
            ),
        ],
        responses={200: BookmarkTopResponseSerializer},
        description="Get the most bookmarked objects across the platform. (Admin only)",
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 10))
            top = BookmarkService.get_top_bookmarked_objects(limit)

            results = []
            for item in top:
                ct_id = item["content_type"]
                obj_id = item["object_id"]
                total = item["total"]
                results.append(
                    {
                        "content_type": ContentType.objects.get_for_id(ct_id).model,
                        "object_id": obj_id,
                        "bookmark_count": total,
                    }
                )

            data = {
                "results": results,
                "limit": limit,
            }
            return Response(
                {
                    "status": True,
                    "message": "Top bookmarked objects retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving top bookmarks")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )