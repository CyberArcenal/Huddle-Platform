import datetime
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from django.utils import timezone
from analytics.models.trend_score import ObjectTrendScore
from analytics.services.trend_score import TrendScoreService
from analytics.serializers.trend_score import (
    TrendScoreDisplaySerializer,
    TrendScoreMinimalSerializer,
    TrendScoreStatisticsSerializer,
)
from global_utils.pagination import AnalyticsPagination

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Input serializers for POST/PUT endpoints
# ----------------------------------------------------------------------
class RecalculateScoreInputSerializer(serializers.Serializer):
    """Input for recalculating a trend score."""
    target_type = serializers.CharField(help_text="Model name (e.g., 'post', 'comment')")
    target_id = serializers.IntegerField(help_text="Object ID")


class CleanupTrendScoreInputSerializer(serializers.Serializer):
    """Input for cleaning up old scores (if needed)."""
    days_inactive = serializers.IntegerField(
        default=90, help_text="Delete scores not updated in this many days"
    )


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_trend_scores(paginator, page, request):
    """
    Construct a paginated data dict that matches the expected structure.
    """
    serializer = TrendScoreMinimalSerializer(page, many=True, context={'request': request})
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
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class PaginatedTrendScoreMinimalSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = TrendScoreMinimalSerializer(many=True)


class TrendScoreObjectGetResponseData(serializers.Serializer):
    trend_score = TrendScoreDisplaySerializer()


class TrendScoreObjectGetResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TrendScoreObjectGetResponseData(allow_null=True)


class TrendScoreObjectPostResponseData(serializers.Serializer):
    trend_score = TrendScoreDisplaySerializer()


class TrendScoreObjectPostResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TrendScoreObjectPostResponseData()


class TrendScoreObjectDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class TrendScoreTopResponseData(serializers.Serializer):
    pagination = PaginatedTrendScoreMinimalSerializer()


class TrendScoreTopResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TrendScoreTopResponseData(allow_null=True)


class TrendScoreStatisticsResponseData(serializers.Serializer):
    stats = TrendScoreStatisticsSerializer()


class TrendScoreStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TrendScoreStatisticsResponseData()


class TrendScoreCleanupResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class TrendScoreObjectView(APIView):
    """
    Get, update, or delete the trend score for a specific object.
    The object is identified by its content type (model name) and ID.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Trend Score"],
        parameters=[
            OpenApiParameter(
                name="target_type",
                type=str,
                description="Model name (e.g., 'post', 'comment')",
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
        responses={200: TrendScoreObjectGetResponseSerializer},
        description="Retrieve the trend score for a specific content object.",
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
            content_type = ContentType.objects.get(model=target_type)
            obj = content_type.get_object_for_this_type(pk=target_id)
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
            return Response(
                {
                    "status": False,
                    "message": f"Object with ID {target_id} not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            score = TrendScoreService.get_score(obj)
            if score is None:
                return Response(
                    {
                        "status": False,
                        "message": "No trend score found for this object",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            ct = ContentType.objects.get_for_model(obj)
            trend_obj = ObjectTrendScore.objects.get(content_type=ct, object_id=obj.id)
            data = TrendScoreDisplaySerializer(trend_obj).data
            return Response(
                {
                    "status": True,
                    "message": "Trend score retrieved.",
                    "data": {"trend_score": data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving trend score for %s:%s", target_type, target_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Trend Score"],
        request=RecalculateScoreInputSerializer,
        responses={200: TrendScoreObjectPostResponseSerializer},
        description="Recalculate the trend score for a content object. (Admin only)",
    )
    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {
                    "status": False,
                    "message": "Admin permission required",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RecalculateScoreInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]

        try:
            content_type = ContentType.objects.get(model=target_type)
            obj = content_type.get_object_for_this_type(pk=target_id)
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
            return Response(
                {
                    "status": False,
                    "message": f"Object with ID {target_id} not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            trend_obj = TrendScoreService.calculate_score(obj)
            data = TrendScoreDisplaySerializer(trend_obj).data
            return Response(
                {
                    "status": True,
                    "message": "Trend score recalculated.",
                    "data": {"trend_score": data},
                }
            )
        except Exception as e:
            logger.exception("Error recalculating trend score for %s:%s", target_type, target_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Trend Score"],
        parameters=[
            OpenApiParameter(
                name="target_type",
                type=str,
                description="Model name",
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
        responses={204: TrendScoreObjectDeleteResponseSerializer},
        description="Delete the trend score for a content object. (Admin only)",
    )
    def delete(self, request):
        if not request.user.is_staff:
            return Response(
                {
                    "status": False,
                    "message": "Admin permission required",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

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
            content_type = ContentType.objects.get(model=target_type)
            obj = content_type.get_object_for_this_type(pk=target_id)
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
            return Response(
                {
                    "status": False,
                    "message": f"Object with ID {target_id} not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            TrendScoreService.delete_score(obj)
            return Response(
                {
                    "status": True,
                    "message": "Trend score deleted.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        except Exception as e:
            logger.exception("Error deleting trend score for %s:%s", target_type, target_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TrendScoreTopView(APIView):
    """List top trending objects (highest scores)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Trend Score"],
        parameters=[
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Filter by content type (model name, e.g., 'post')",
                required=False,
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of results per page (default 20)",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page (overrides limit)",
                required=False,
            ),
        ],
        responses={200: TrendScoreTopResponseSerializer},
        description="Retrieve the top trending objects, optionally filtered by content type.",
    )
    def get(self, request):
        content_type_filter = request.query_params.get("content_type")
        limit = int(request.query_params.get("limit", 20))

        try:
            queryset = ObjectTrendScore.objects.select_related("content_type").order_by(
                "-score"
            )

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
            paginator.page_size = limit
            page = paginator.paginate_queryset(queryset, request)
            paginated_data = wrap_paginated_trend_scores(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Top trending objects retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving top trending objects")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TrendScoreStatisticsView(APIView):
    """Aggregate statistics for trend scores."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Trend Score"],
        responses={200: TrendScoreStatisticsResponseSerializer},
        description="Get average, highest, and lowest trend scores across all objects.",
    )
    def get(self, request):
        try:
            stats = {
                "average_score": TrendScoreService.get_average_score(),
                "highest_score": TrendScoreService.get_highest_score(),
                "lowest_score": TrendScoreService.get_lowest_score(),
            }
            return Response(
                {
                    "status": True,
                    "message": "Trend score statistics retrieved.",
                    "data": {"stats": stats},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving trend score statistics")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TrendScoreCleanupView(APIView):
    """
    Clean up old or stale trend scores.
    This endpoint is for admin use to delete scores that haven't been updated in a while.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Trend Score"],
        request=CleanupTrendScoreInputSerializer,
        responses={200: TrendScoreCleanupResponseSerializer},
        description="Delete trend scores that haven't been updated in more than the specified days. (Admin only)",
    )
    @transaction.atomic
    def post(self, request):
        serializer = CleanupTrendScoreInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        days = serializer.validated_data["days_inactive"]
        cutoff = timezone.now() - datetime.timedelta(days=days)

        try:
            count, _ = ObjectTrendScore.objects.filter(calculated_at__lt=cutoff).delete()
            return Response(
                {
                    "status": True,
                    "message": f"Deleted {count} stale trend score records.",
                    "data": None,
                }
            )
        except Exception as e:
            logger.exception("Error cleaning up stale trend scores")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )