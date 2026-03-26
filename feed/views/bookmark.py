from rest_framework.views import APIView
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
from global_utils.pagination import AnalyticsPagination


# ----- Input serializers for add/remove endpoints -----
class BookmarkActionSerializer(serializers.Serializer):
    target_type = serializers.CharField(help_text="Model name (e.g., 'post', 'comment')")
    target_id = serializers.IntegerField(help_text="Object ID")


# ----- Paginated response serializer for bookmark list -----
class PaginatedBookmarkMinimalSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = BookmarkMinimalSerializer(many=True)


# ----- View classes -----
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
        responses={200: PaginatedBookmarkMinimalSerializer},
        description="Get all bookmarks created by the current user.",
    )
    def get(self, request):
        queryset = ObjectBookmark.objects.filter(user=request.user).select_related(
            "user", "content_type"
        ).order_by("-created_at")

        content_type_filter = request.query_params.get("content_type")
        if content_type_filter:
            try:
                ct = ContentType.objects.get(model=content_type_filter)
                queryset = queryset.filter(content_type=ct)
            except ContentType.DoesNotExist:
                return Response(
                    {"error": f"Invalid content type: {content_type_filter}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        paginator = AnalyticsPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = BookmarkMinimalSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class BookmarkDetailView(APIView):
    """Add or remove a bookmark for a specific object."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Bookmarks"],
        request=BookmarkActionSerializer,
        responses={201: BookmarkDisplaySerializer},
        description="Create a bookmark for the given object.",
    )
    def post(self, request):
        serializer = BookmarkActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]

        try:
            ct = ContentType.objects.get(model=target_type)
            obj = ct.get_object_for_this_type(pk=target_id)
        except ContentType.DoesNotExist:
            return Response(
                {"error": f"Invalid content type: {target_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except obj.DoesNotExist:
            return Response(
                {"error": f"Object with ID {target_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        bookmark = BookmarkService.add_bookmark(user=request.user, obj=obj)
        serializer = BookmarkDisplaySerializer(
            bookmark, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Bookmarks"],
        request=BookmarkActionSerializer,
        responses={204: None},
        description="Remove a bookmark for the given object.",
    )
    def delete(self, request):
        serializer = BookmarkActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]

        try:
            ct = ContentType.objects.get(model=target_type)
            obj = ct.get_object_for_this_type(pk=target_id)
        except ContentType.DoesNotExist:
            return Response(
                {"error": f"Invalid content type: {target_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except obj.DoesNotExist:
            # If the object doesn't exist, we can still remove bookmarks if any exist
            # But we need to handle gracefully
            # Actually, we need the content type to filter, but we can use the provided type
            pass

        BookmarkService.remove_bookmark(user=request.user, obj=obj)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        responses={200: BookmarkStatisticsSerializer},
        description="Get total bookmarks for the object and whether the current user has bookmarked it.",
    )
    def get(self, request):
        target_type = request.query_params.get("target_type")
        target_id = request.query_params.get("target_id")

        if not target_type or not target_id:
            return Response(
                {"error": "target_type and target_id are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ct = ContentType.objects.get(model=target_type)
            obj = ct.get_object_for_this_type(pk=target_id)
        except ContentType.DoesNotExist:
            return Response(
                {"error": f"Invalid content type: {target_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except obj.DoesNotExist:
            # Object doesn't exist, but we can still return zero stats
            stats = {
                "bookmark_count": 0,
                "has_bookmarked": False,
            }
            serializer = BookmarkStatisticsSerializer(stats)
            return Response(serializer.data)

        stats = {
            "bookmark_count": BookmarkService.get_bookmark_count(obj),
            "has_bookmarked": BookmarkService.has_bookmarked(request.user, obj),
        }
        serializer = BookmarkStatisticsSerializer(stats)
        return Response(serializer.data)


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
        responses={200: BookmarkMinimalSerializer(many=True)},
        description="Get the most bookmarked objects across the platform. (Admin only)",
    )
    def get(self, request):
        limit = int(request.query_params.get("limit", 10))
        content_type_filter = request.query_params.get("content_type")

        top = BookmarkService.get_top_bookmarked_objects(limit)

        # top is a list of dicts with content_type, object_id, total
        # We need to fetch the actual objects to get their details.
        # Alternatively, we can return the aggregated data without the objects.
        # Let's return a simplified list of content_type, object_id, bookmark_count.
        results = []
        for item in top:
            ct_id = item["content_type"]
            obj_id = item["object_id"]
            total = item["total"]
            # Optionally load the object if needed, but we'll just return the ids.
            results.append({
                "content_type": ContentType.objects.get_for_id(ct_id).model,
                "object_id": obj_id,
                "bookmark_count": total,
            })

        # Or we could serialize as BookmarkMinimalSerializer with dummy objects? Not ideal.
        # We'll just return a custom list.
        return Response(results)