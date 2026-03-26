from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.contenttypes.models import ContentType
from django.db import models
from drf_spectacular.utils import extend_schema, OpenApiParameter

from feed.models.view import ObjectView
from feed.services.view import ViewService
from feed.serializers.view import (
    ViewDisplaySerializer,
    ViewMinimalSerializer,
    ViewCreateSerializer,
    ViewStatisticsSerializer,
)
from global_utils.pagination import AnalyticsPagination, StoriesPagination
from stories.services.story import StoryService


# ----- Paginated response serializer for view history -----
class PaginatedViewMinimalSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ViewMinimalSerializer(many=True)


class ViewRecordView(APIView):
    """Record a view for a content object."""

    permission_classes = []  # Public endpoint (allow unauthenticated)

    @extend_schema(
        tags=["Views"],
        request=ViewCreateSerializer,
        responses={201: ViewDisplaySerializer},
        description="Record a view for a content object. Can be anonymous or authenticated.",
    )
    def post(self, request):
        serializer = ViewCreateSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        view = serializer.save()
        view_serializer = ViewDisplaySerializer(view, context={"request": request})
        return Response(view_serializer.data, status=status.HTTP_201_CREATED)


class ViewStatisticsView(APIView):
    """Get view statistics for a specific content object."""

    permission_classes = []  # Public endpoint

    @extend_schema(
        tags=["Views"],
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
        responses={200: ViewStatisticsSerializer},
        description="Get aggregated view statistics for a content object.",
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
            # Object doesn't exist, return zero stats
            stats = {
                "view_count": 0,
                "unique_viewers": 0,
                "total_duration": 0,
                "average_duration": 0,
            }
            serializer = ViewStatisticsSerializer(stats)
            return Response(serializer.data)

        stats = {
            "view_count": ViewService.get_view_count(obj),
            "unique_viewers": ViewService.get_unique_viewers(obj),
            "total_duration": ViewService.get_total_duration(obj),
            "average_duration": ViewService.get_average_duration(obj),
        }
        serializer = ViewStatisticsSerializer(stats)
        return Response(serializer.data)


class ViewHistoryView(APIView):
    """List view history for the authenticated user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Views"],
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
        responses={200: PaginatedViewMinimalSerializer},
        description="Get the current user's view history.",
    )
    def get(self, request):
        queryset = ObjectView.objects.filter(user=request.user).select_related(
            "user", "content_type"
        ).order_by("-viewed_at")

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
        serializer = ViewMinimalSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class TopViewedView(APIView):
    """List most viewed objects globally (admin only)."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Views"],
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
        responses={200: ViewStatisticsSerializer(many=True)},
        description="Get the most viewed objects across the platform. (Admin only)",
    )
    def get(self, request):
        limit = int(request.query_params.get("limit", 10))
        content_type_filter = request.query_params.get("content_type")

        queryset = ObjectView.objects.values("content_type", "object_id").annotate(
            view_count=models.Count("id"),
            unique_viewers=models.Count("user", distinct=True),
            total_duration=models.Sum("duration_seconds"),
            average_duration=models.Avg("duration_seconds"),
        ).order_by("-view_count")[:limit]

        if content_type_filter:
            try:
                ct = ContentType.objects.get(model=content_type_filter)
                queryset = queryset.filter(content_type=ct)
            except ContentType.DoesNotExist:
                return Response(
                    {"error": f"Invalid content type: {content_type_filter}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        results = []
        for item in queryset:
            ct_id = item["content_type"]
            obj_id = item["object_id"]
            try:
                ct = ContentType.objects.get_for_id(ct_id)
                model_name = ct.model
            except ContentType.DoesNotExist:
                model_name = "unknown"

            results.append({
                "target_type": model_name,
                "target_id": obj_id,
                "view_count": item["view_count"],
                "unique_viewers": item["unique_viewers"],
                "total_duration": item["total_duration"],
                "average_duration": item["average_duration"],
            })

        return Response(results)
    


class ViewsListView(APIView):
    """Get views for a specific story"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Views"],
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
        responses={200: PaginatedViewMinimalSerializer},
        description="Retrieve a paginated list of users who viewed a story. Only the story owner can access.",
    )
    def get(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {"error": "Story not found"}, status=status.HTTP_404_NOT_FOUND
            )
        # Permission check: only owner or admin can see viewers
        if story.user != request.user and not request.user.is_staff:
            return Response(
                {"error": "You do not have permission to view viewers of this story"},
                status=status.HTTP_403_FORBIDDEN,
            )
        views = ViewService.get_story_views(story)
        paginator = StoriesPagination()
        page = paginator.paginate_queryset(views, request)
        serializer = ViewMinimalSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)