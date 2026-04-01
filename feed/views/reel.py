import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from feed.services.reaction import ReactionService
from users.models import User
from feed.models import Reel
from feed.serializers.reel import (
    ReelCreateSerializer,
    ReelUpdateSerializer,
    ReelDisplaySerializer,
)
from feed.services.reel import ReelService
from global_utils.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class ReelCreateResponseData(serializers.Serializer):
    id = serializers.IntegerField()
    processing = serializers.BooleanField()


class ReelCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ReelCreateResponseData(allow_null=True)


class ReelStatusResponseData(serializers.Serializer):
    id = serializers.IntegerField()
    processing = serializers.BooleanField()
    ready = serializers.BooleanField()
    video_url = serializers.CharField(allow_null=True, required=False)


class ReelStatusResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ReelStatusResponseData(allow_null=True)


class ReelDetailResponseData(serializers.Serializer):
    reel = ReelDisplaySerializer()


class ReelDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ReelDetailResponseData(allow_null=True)


class ReelUpdateResponseData(serializers.Serializer):
    reel = ReelDisplaySerializer()


class ReelUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ReelUpdateResponseData(allow_null=True)


class ReelDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class PaginatedReelSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ReelDisplaySerializer(many=True)


class ReelListResponseData(serializers.Serializer):
    pagination = PaginatedReelSerializer()


class ReelListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ReelListResponseData(allow_null=True)


class ReelSearchResponseData(serializers.Serializer):
    pagination = PaginatedReelSerializer()


class ReelSearchResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ReelSearchResponseData(allow_null=True)


class TrendingReelsResponseData(serializers.Serializer):
    reels = ReelDisplaySerializer(many=True)
    hours = serializers.IntegerField()
    min_likes = serializers.IntegerField()
    limit = serializers.IntegerField()


class TrendingReelsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TrendingReelsResponseData()


class ReelStatisticsResponseData(serializers.Serializer):
    reel_id = serializers.IntegerField()
    like_count = serializers.IntegerField()
    comment_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    privacy = serializers.CharField()


class ReelStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ReelStatisticsResponseData()


class UserReelStatisticsResponseData(serializers.Serializer):
    total_reels = serializers.IntegerField()
    public_reels = serializers.IntegerField()
    private_reels = serializers.IntegerField()
    privacy_breakdown = serializers.ListField(child=serializers.DictField())
    total_reactions = serializers.IntegerField()
    first_reel_date = serializers.DateTimeField(allow_null=True)


class UserReelStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserReelStatisticsResponseData()


class ReelRestoreResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ReelDisplaySerializer(allow_null=True)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_data(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedReelSerializer.
    """
    serializer = ReelDisplaySerializer(page, many=True, context={'request': request})
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

class ReelStatusView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Reel's"],
        responses={200: ReelStatusResponseSerializer},
        description="Check the processing status of a reel. Returns whether the reel is still being processed and the video URL when ready.",
    )
    def get(self, request, reel_id):
        reel = get_object_or_404(Reel, id=reel_id)
        if reel.privacy != "public" and request.user != reel.user:
            return Response(
                {
                    "status": False,
                    "message": "Forbidden",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        data = {
            "id": reel.id,
            "processing": reel.processing,
            "ready": not reel.processing and reel.media.exists(),
            "video_url": (
                request.build_absolute_uri(reel.media.first().file.url)
                if reel.media.exists()
                else None
            ),
        }
        return Response(
            {
                "status": True,
                "message": "Reel status retrieved.",
                "data": data,
            }
        )


class ReelListView(APIView):
    """View for listing and creating reels"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["Reel's"],
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="Filter by user ID (returns that user's reels)",
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
        responses={200: ReelListResponseSerializer},
        description=(
            "List reels. If user_id provided, returns reels of that user. "
            "If authenticated and no user_id, returns feed (followed users + own). "
            "Otherwise returns public reels."
        ),
    )
    def get(self, request):
        user_id = request.query_params.get("user_id")
        try:
            if user_id:
                user = get_object_or_404(User, id=user_id)
                include_processing = request.user.is_authenticated and request.user == user
                reels = ReelService.get_user_reels(
                    user=user,
                    requester=request.user if request.user.is_authenticated else None,
                    include_processing=include_processing,
                )
            else:
                if request.user.is_authenticated:
                    reels = ReelService.get_feed_reels(
                        user=request.user, include_processing=False
                    )
                else:
                    reels = ReelService.get_public_reels(include_processing=False)

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(reels, request)
            paginated_data = wrap_paginated_data(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Reels retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error listing reels")
            return Response(
                {
                    "status": False,
                    "message": "something went wrong",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Reel's"],
        request={
            "multipart/form-data": ReelCreateSerializer,
        },
        responses={
            202: ReelCreateResponseSerializer,
            400: ReelCreateResponseSerializer,
        },
        description="Create a new reel.",
    )
    @transaction.atomic
    def post(self, request):
        logger.debug(f"Post request: {request.data}")
        serializer = ReelCreateSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            reel = serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Reel upload accepted, processing in background.",
                    "data": {
                        "id": reel.id,
                        "processing": True,
                    },
                },
                status=status.HTTP_202_ACCEPTED,
            )

        logger.debug("Reel create validation errors: %s", serializer.errors)
        return Response(
            {
                "status": False,
                "message": "Failed to create reel.",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class ReelDetailView(APIView):
    """View for retrieving, updating, and deleting a specific reel"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_object(self, reel_id):
        return get_object_or_404(Reel, id=reel_id, is_deleted=False)

    def _check_privacy(self, reel, user):
        """Check if user can view this reel based on privacy."""
        if reel.privacy == "public":
            return True
        if reel.privacy == "followers":
            if user.is_authenticated and (
                user == reel.user or reel.user.followers.filter(id=user.id).exists()
            ):
                return True
            return False
        if reel.privacy == "secret":
            return user.is_authenticated and user == reel.user
        return False

    @extend_schema(
        tags=["Reel's"],
        responses={200: ReelDetailResponseSerializer},
        description="Retrieve a single reel by ID.",
    )
    def get(self, request, reel_id):
        reel = self.get_object(reel_id)
        if not self._check_privacy(reel, request.user):
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view this reel",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        data = ReelDisplaySerializer(reel, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Reel retrieved.",
                "data": {"reel": data},
            }
        )

    @extend_schema(
        tags=["Reel's"],
        request=ReelUpdateSerializer,
        responses={200: ReelUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update reel",
                value={"caption": "Updated caption", "privacy": "followers"},
                request_only=True,
            )
        ],
        description="Update a reel (partial updates allowed). Only owner can update.",
    )
    @transaction.atomic
    def put(self, request, reel_id):
        reel = self.get_object(reel_id)
        if request.user != reel.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to update this reel",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ReelUpdateSerializer(
            reel, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            updated_reel = serializer.save()
            data = ReelDisplaySerializer(updated_reel, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Reel updated successfully.",
                    "data": {"reel": data},
                }
            )
        return Response(
            {
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        tags=["Reel's"],
        responses={200: ReelDeleteResponseSerializer},
        description="Delete a reel (soft delete). Only owner can delete.",
    )
    @transaction.atomic
    def delete(self, request, reel_id):
        reel = self.get_object(reel_id)
        if request.user != reel.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to delete this reel",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        success = ReelService.delete_reel(reel, soft_delete=True)
        if success:
            return Response(
                {
                    "status": True,
                    "message": "Reel deleted successfully",
                    "data": None,
                }
            )
        return Response(
            {
                "status": False,
                "message": "Failed to delete reel",
                "data": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ReelSearchView(APIView):
    """Search reels by caption."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Reel's"],
        parameters=[
            OpenApiParameter(
                name="q", type=str, description="Search query", required=True
            ),
            OpenApiParameter(
                name="user_id",
                type=int,
                description="Filter by user ID",
                required=False,
            ),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: ReelSearchResponseSerializer},
        description="Search reels by caption.",
    )
    def get(self, request):
        query = request.query_params.get("q", "")
        user_id = request.query_params.get("user_id")

        if not query:
            return Response(
                {
                    "status": False,
                    "message": "Query parameter 'q' is required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = None
        if user_id:
            user = get_object_or_404(User, id=user_id)

        try:
            reels = ReelService.search_reels(
                query=query, user=user, include_processing=False
            )

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(reels, request)
            paginated_data = wrap_paginated_data(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Search results.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error searching reels")
            return Response(
                {
                    "status": False,
                    "message": "something went wrong",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TrendingReelsView(APIView):
    """Get trending reels (most liked recently)."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Reel's"],
        parameters=[
            OpenApiParameter(
                name="hours",
                type=int,
                description="Time window in hours",
                required=False,
            ),
            OpenApiParameter(
                name="min_likes", type=int, description="Minimum likes", required=False
            ),
            OpenApiParameter(
                name="limit", type=int, description="Max results", required=False
            ),
        ],
        responses={200: TrendingReelsResponseSerializer},
        description="Get trending reels based on like count in the last N hours.",
    )
    def get(self, request):
        hours = int(request.query_params.get("hours", 24))
        min_likes = int(request.query_params.get("min_likes", 5))
        limit = int(request.query_params.get("limit", 10))

        try:
            trending = ReelService.get_trending_reels(
                hours=hours, min_likes=min_likes, limit=limit, include_processing=False
            )
            reels = [item["reel"] for item in trending]
            serializer = ReelDisplaySerializer(
                reels, many=True, context={"request": request}
            )
            return Response(
                {
                    "status": True,
                    "message": "Trending reels retrieved.",
                    "data": {
                        "reels": serializer.data,
                        "hours": hours,
                        "min_likes": min_likes,
                        "limit": limit,
                    },
                }
            )
        except Exception as e:
            logger.exception("Error fetching trending reels")
            return Response(
                {
                    "status": False,
                    "message": "something went wrong",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ReelStatisticsView(APIView):
    """Get statistics for a single reel."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Reel's"],
        responses={200: ReelStatisticsResponseSerializer},
        description="Get like and comment counts for a reel.",
    )
    def get(self, request, reel_id):
        reel = get_object_or_404(Reel, id=reel_id, is_deleted=False)

        # Privacy check
        if reel.privacy != "public" and request.user != reel.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view statistics for this reel",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        stats = ReelService.get_reel_statistics(reel)
        return Response(
            {
                "status": True,
                "message": "Statistics retrieved.",
                "data": stats,
            }
        )


class ReelRestoreView(APIView):
    """Restore a soft-deleted reel."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Reel's"],
        responses={
            200: ReelRestoreResponseSerializer,
            403: ReelRestoreResponseSerializer,
            400: ReelRestoreResponseSerializer,
            500: ReelRestoreResponseSerializer,
        },
        description="Restore a soft‑deleted reel. Only owner can restore.",
    )
    @transaction.atomic
    def post(self, request, reel_id):
        reel = get_object_or_404(Reel, id=reel_id, is_deleted=True)

        if request.user != reel.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to restore this reel.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        success = ReelService.restore_reel(reel)
        if success:
            return Response(
                {
                    "status": True,
                    "message": "Reel restored successfully.",
                    "data": ReelDisplaySerializer(
                        reel, context={"request": request}
                    ).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": False,
                "message": "Failed to restore reel.",
                "data": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class UserReelStatisticsView(APIView):
    """Get reel statistics for a user."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Reel's"],
        responses={200: UserReelStatisticsResponseSerializer},
        description="Get statistics for a user's reels.",
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
        else:
            # /users/me/... case
            if not request.user.is_authenticated:
                return Response(
                    {
                        "status": False,
                        "message": "Authentication required",
                        "data": None,
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            target_user = request.user

        try:
            # Privacy: if target user has secret/followers reels, only they can see full stats
            if request.user != target_user:
                # Return only public stats
                public_reels = Reel.objects.filter(
                    user=target_user, privacy="public", is_deleted=False, processing=False
                )
                total_reels = public_reels.count()
                privacy_breakdown = [{"privacy": "public", "count": total_reels}]
                total_reactions = 0
                for reel in public_reels:
                    total_reactions += ReactionService.get_like_count("reel", reel.id)
                first_reel = public_reels.order_by("created_at").first()
                first_reel_date = first_reel.created_at if first_reel else None
                data = {
                    "total_reels": total_reels,
                    "public_reels": total_reels,
                    "private_reels": 0,
                    "privacy_breakdown": privacy_breakdown,
                    "total_reactions": total_reactions,
                    "first_reel_date": first_reel_date,
                }
            else:
                stats = ReelService.get_user_reel_statistics(target_user)
                data = {
                    "total_reels": stats["total_reels"],
                    "public_reels": stats["public_reels"],
                    "private_reels": stats["private_reels"],
                    "privacy_breakdown": stats["privacy_breakdown"],
                    "total_reactions": stats["total_reactions"],
                    "first_reel_date": stats["first_reel_date"],
                }

            return Response(
                {
                    "status": True,
                    "message": "User statistics retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error fetching user reel statistics")
            return Response(
                {
                    "status": False,
                    "message": "something went wrong",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )