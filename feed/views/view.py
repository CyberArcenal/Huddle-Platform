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

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class ViewRecordResponseData(serializers.Serializer):
    view = ViewDisplaySerializer()


class ViewRecordResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ViewRecordResponseData(allow_null=True)


class ViewStatisticsResponseData(serializers.Serializer):
    stats = ViewStatisticsSerializer()


class ViewStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ViewStatisticsResponseData()


class PaginatedViewMinimalSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ViewMinimalSerializer(many=True)


class ViewHistoryResponseData(serializers.Serializer):
    pagination = PaginatedViewMinimalSerializer()


class ViewHistoryResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ViewHistoryResponseData(allow_null=True)


class TopViewedItemSerializer(serializers.Serializer):
    target_type = serializers.CharField()
    target_id = serializers.IntegerField()
    view_count = serializers.IntegerField()
    unique_viewers = serializers.IntegerField()
    total_duration = serializers.IntegerField(allow_null=True)
    average_duration = serializers.FloatField(allow_null=True)


class TopViewedResponseData(serializers.Serializer):
    results = TopViewedItemSerializer(many=True)
    limit = serializers.IntegerField()


class TopViewedResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TopViewedResponseData()


class StoryViewsResponseData(serializers.Serializer):
    pagination = PaginatedViewMinimalSerializer()


class StoryViewsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryViewsResponseData(allow_null=True)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_views(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedViewMinimalSerializer.
    """
    serializer = ViewMinimalSerializer(page, many=True, context={'request': request})
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

class ViewRecordView(APIView):
    """Record a view for a content object."""

    permission_classes = []  # Public endpoint (allow unauthenticated)

    @extend_schema(
        tags=["Views"],
        request=ViewCreateSerializer,
        responses={201: ViewRecordResponseSerializer},
        description="Record a view for a content object. Can be anonymous or authenticated.",
    )
    def post(self, request):
        serializer = ViewCreateSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        view = serializer.save()
        view_data = ViewDisplaySerializer(view, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "View recorded successfully.",
                "data": {"view": view_data},
            },
            status=status.HTTP_201_CREATED,
        )


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
        responses={200: ViewStatisticsResponseSerializer},
        description="Get aggregated view statistics for a content object.",
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
            obj = ct.get_object_for_this_type(pk=target_id)
        except ContentType.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": f"Invalid content type: {target_type}",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            # Object doesn't exist, return zero stats
            stats = {
                "view_count": 0,
                "unique_viewers": 0,
                "total_duration": 0,
                "average_duration": 0,
            }
            return Response(
                {
                    "status": True,
                    "message": "Statistics retrieved (object not found, zero stats).",
                    "data": {"stats": stats},
                }
            )

        stats = {
            "view_count": ViewService.get_view_count(obj),
            "unique_viewers": ViewService.get_unique_viewers(obj),
            "total_duration": ViewService.get_total_duration(obj),
            "average_duration": ViewService.get_average_duration(obj),
        }
        return Response(
            {
                "status": True,
                "message": "Statistics retrieved.",
                "data": {"stats": stats},
            }
        )


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
        responses={200: ViewHistoryResponseSerializer},
        description="Get the current user's view history.",
    )
    def get(self, request):
        try:
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
                        {
                            "status": False,
                            "message": f"Invalid content type: {content_type_filter}",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            paginator = AnalyticsPagination()
            page = paginator.paginate_queryset(queryset, request)
            paginated_data = wrap_paginated_views(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "View history retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving view history")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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
        responses={200: TopViewedResponseSerializer},
        description="Get the most viewed objects across the platform. (Admin only)",
    )
    def get(self, request):
        try:
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
                        {
                            "status": False,
                            "message": f"Invalid content type: {content_type_filter}",
                            "data": None,
                        },
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
                    "total_duration": item["total_duration"] or 0,
                    "average_duration": item["average_duration"] or 0.0,
                })

            data = {
                "results": results,
                "limit": limit,
            }
            return Response(
                {
                    "status": True,
                    "message": "Top viewed objects retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving top viewed objects")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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
        responses={200: StoryViewsResponseSerializer},
        description="Retrieve a paginated list of users who viewed a story. Only the story owner can access.",
    )
    def get(self, request, story_id):
        try:
            story = StoryService.get_story_by_id(story_id)
            if not story:
                return Response(
                    {
                        "status": False,
                        "message": "Story not found",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Permission check: only owner or admin can see viewers
            if story.user != request.user and not request.user.is_staff:
                return Response(
                    {
                        "status": False,
                        "message": "You do not have permission to view viewers of this story",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            views = ViewService.get_story_views(story)
            paginator = StoriesPagination()
            page = paginator.paginate_queryset(views, request)
            paginated_data = wrap_paginated_views(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Story viewers retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving story viewers for story %s", story_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )