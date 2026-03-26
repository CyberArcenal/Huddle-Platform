import datetime

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


# ----- Input serializers for POST/PUT endpoints -----
class RecalculateScoreInputSerializer(serializers.Serializer):
    """Input for recalculating a trend score."""
    target_type = serializers.CharField(help_text="Model name (e.g., 'post', 'comment')")
    target_id = serializers.IntegerField(help_text="Object ID")


class CleanupTrendScoreInputSerializer(serializers.Serializer):
    """Input for cleaning up old scores (if needed)."""
    days_inactive = serializers.IntegerField(
        default=90, help_text="Delete scores not updated in this many days"
    )


# ----- Paginated response serializer for top trending list -----
class PaginatedTrendScoreMinimalSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = TrendScoreMinimalSerializer(many=True)


# ----- View classes -----
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
        responses={200: TrendScoreDisplaySerializer},
        description="Retrieve the trend score for a specific content object.",
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
            content_type = ContentType.objects.get(model=target_type)
            obj = content_type.get_object_for_this_type(pk=target_id)
        except ContentType.DoesNotExist:
            return Response(
                {"error": f"Invalid content type: {target_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except obj.DoesNotExist:  # model class's DoesNotExist
            return Response(
                {"error": f"Object with ID {target_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        score = TrendScoreService.get_score(obj)
        if score is None:
            # Optionally, you could auto-calculate if missing, but we'll just return 404
            return Response(
                {"error": "No trend score found for this object"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Retrieve the full ObjectTrendScore record to get id and calculated_at
        ct = ContentType.objects.get_for_model(obj)
        trend_obj = ObjectTrendScore.objects.get(content_type=ct, object_id=obj.id)
        serializer = TrendScoreDisplaySerializer(trend_obj)
        return Response(serializer.data)

    @extend_schema(
        tags=["Trend Score"],
        request=RecalculateScoreInputSerializer,
        responses={200: TrendScoreDisplaySerializer},
        description="Recalculate the trend score for a content object. (Admin only)",
    )
    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "Admin permission required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RecalculateScoreInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]

        try:
            content_type = ContentType.objects.get(model=target_type)
            obj = content_type.get_object_for_this_type(pk=target_id)
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

        trend_obj = TrendScoreService.calculate_score(obj)
        serializer = TrendScoreDisplaySerializer(trend_obj)
        return Response(serializer.data)

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
        responses={204: None},
        description="Delete the trend score for a content object. (Admin only)",
    )
    def delete(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "Admin permission required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        target_type = request.query_params.get("target_type")
        target_id = request.query_params.get("target_id")

        if not target_type or not target_id:
            return Response(
                {"error": "target_type and target_id are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            content_type = ContentType.objects.get(model=target_type)
            obj = content_type.get_object_for_this_type(pk=target_id)
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

        TrendScoreService.delete_score(obj)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        responses={200: PaginatedTrendScoreMinimalSerializer},
        description="Retrieve the top trending objects, optionally filtered by content type.",
    )
    def get(self, request):
        content_type_filter = request.query_params.get("content_type")
        limit = int(request.query_params.get("limit", 20))

        queryset = ObjectTrendScore.objects.select_related("content_type").order_by(
            "-score"
        )

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
        paginator.page_size = limit
        page = paginator.paginate_queryset(queryset, request)
        serializer = TrendScoreMinimalSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class TrendScoreStatisticsView(APIView):
    """Aggregate statistics for trend scores."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Trend Score"],
        responses={200: TrendScoreStatisticsSerializer},
        description="Get average, highest, and lowest trend scores across all objects.",
    )
    def get(self, request):
        stats = {
            "average_score": TrendScoreService.get_average_score(),
            "highest_score": TrendScoreService.get_highest_score(),
            "lowest_score": TrendScoreService.get_lowest_score(),
        }
        serializer = TrendScoreStatisticsSerializer(stats)
        return Response(serializer.data)


class TrendScoreCleanupView(APIView):
    """
    Clean up old or stale trend scores.
    This endpoint is for admin use to delete scores that haven't been updated in a while.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Trend Score"],
        request=CleanupTrendScoreInputSerializer,
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        description="Delete trend scores that haven't been updated in more than the specified days. (Admin only)",
    )
    @transaction.atomic
    def post(self, request):
        serializer = CleanupTrendScoreInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        days = serializer.validated_data["days_inactive"]
        cutoff = timezone.now() - datetime.timedelta(days=days)

        count, _ = ObjectTrendScore.objects.filter(calculated_at__lt=cutoff).delete()
        return Response({"message": f"Deleted {count} stale trend score records."})