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


class PaginatedReelSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ReelDisplaySerializer(many=True)


class ReelListView(APIView):
    """View for listing and creating reels"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
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
        responses={200: PaginatedReelSerializer},
        description=(
            "List reels. If user_id provided, returns reels of that user. "
            "If authenticated and no user_id, returns feed (followed users + own). "
            "Otherwise returns public reels."
        ),
    )
    def get(self, request):
        user_id = request.query_params.get("user_id")
        if user_id:
            user = get_object_or_404(User, id=user_id)
            reels = ReelService.get_user_reels(user=user, include_deleted=False)
        else:
            if request.user.is_authenticated:
                reels = ReelService.get_feed_reels(user=request.user)
            else:
                reels = ReelService.get_public_reels()

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(reels, request)
        serializer = ReelDisplaySerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=ReelCreateSerializer,
        responses={201: ReelDisplaySerializer},
        examples=[
            OpenApiExample(
                "Create reel",
                value={
                    "caption": "My first reel",
                    "video": "(binary file)",
                    "thumbnail": "(binary file, optional)",
                    "audio": "(binary file, optional)",
                    "duration": 15.5,
                    "privacy": "public",
                },
                request_only=True,
            )
        ],
        description="Create a new reel.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = ReelCreateSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            reel = serializer.save()
            return Response(
                ReelDisplaySerializer(reel, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        responses={200: ReelDisplaySerializer},
        description="Retrieve a single reel by ID.",
    )
    def get(self, request, reel_id):
        reel = self.get_object(reel_id)
        if not self._check_privacy(reel, request.user):
            return Response(
                {"error": "You do not have permission to view this reel"},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ReelDisplaySerializer(reel, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=ReelUpdateSerializer,
        responses={200: ReelDisplaySerializer},
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
                {"error": "You do not have permission to update this reel"},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ReelUpdateSerializer(
            reel, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            updated_reel = serializer.save()
            return Response(
                ReelDisplaySerializer(updated_reel, context={"request": request}).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        description="Delete a reel (soft delete). Only owner can delete.",
    )
    @transaction.atomic
    def delete(self, request, reel_id):
        reel = self.get_object(reel_id)
        if request.user != reel.user:
            return Response(
                {"error": "You do not have permission to delete this reel"},
                status=status.HTTP_403_FORBIDDEN,
            )
        success = ReelService.delete_reel(reel, soft_delete=True)
        if success:
            return Response({"message": "Reel deleted successfully"})
        return Response(
            {"error": "Failed to delete reel"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        
# feed/views/reel.py (append to existing)

class ReelSearchView(APIView):
    """Search reels by caption."""
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='q', type=str, description='Search query', required=True),
            OpenApiParameter(name='user_id', type=int, description='Filter by user ID', required=False),
            OpenApiParameter(name='page', type=int, required=False),
            OpenApiParameter(name='page_size', type=int, required=False),
        ],
        responses={200: PaginatedReelSerializer},
        description="Search reels by caption."
    )
    def get(self, request):
        query = request.query_params.get('q', '')
        user_id = request.query_params.get('user_id')
        
        if not query:
            return Response(
                {"error": "Query parameter 'q' is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = None
        if user_id:
            user = get_object_or_404(User, id=user_id)
        
        reels = ReelService.search_reels(query=query, user=user)
        
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(reels, request)
        serializer = ReelDisplaySerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class TrendingReelsView(APIView):
    """Get trending reels (most liked recently)."""
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='hours', type=int, description='Time window in hours', required=False),
            OpenApiParameter(name='min_likes', type=int, description='Minimum likes', required=False),
            OpenApiParameter(name='limit', type=int, description='Max results', required=False),
        ],
        responses={
            200: ReelDisplaySerializer(many=True)
        },
        description="Get trending reels based on like count in the last N hours."
    )
    def get(self, request):
        hours = int(request.query_params.get('hours', 24))
        min_likes = int(request.query_params.get('min_likes', 5))
        limit = int(request.query_params.get('limit', 10))
        
        trending = ReelService.get_trending_reels(hours=hours, min_likes=min_likes, limit=limit)
        
        # Extract just the reel objects for serialization
        reels = [item['reel'] for item in trending]
        serializer = ReelDisplaySerializer(reels, many=True, context={'request': request})
        return Response(serializer.data)


class ReelStatisticsView(APIView):
    """Get statistics for a single reel."""
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'reel_id': {'type': 'integer'},
                    'like_count': {'type': 'integer'},
                    'comment_count': {'type': 'integer'},
                    'created_at': {'type': 'string', 'format': 'date-time'},
                    'privacy': {'type': 'string'}
                }
            }
        },
        description="Get like and comment counts for a reel."
    )
    def get(self, request, reel_id):
        reel = get_object_or_404(Reel, id=reel_id, is_deleted=False)
        
        # Privacy check
        if reel.privacy != 'public' and request.user != reel.user:
            return Response(
                {"error": "You do not have permission to view statistics for this reel"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        stats = ReelService.get_reel_statistics(reel)
        return Response(stats)
    
    
class ReelRestoreResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    reel = ReelDisplaySerializer()


class ReelRestoreView(APIView):
    """Restore a soft-deleted reel."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: ReelRestoreResponseSerializer},
        description="Restore a soft‑deleted reel. Only owner can restore."
    )
    def post(self, request, reel_id):
        reel = get_object_or_404(Reel, id=reel_id, is_deleted=True)
        
        if request.user != reel.user:
            return Response(
                {"error": "You do not have permission to restore this reel"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        success = ReelService.restore_reel(reel)
        if success:
            data = ReelDisplaySerializer(reel, context={'request': request}).data
            return Response({
                'message': 'Reel restored successfully',
                'reel': data
            })
        return Response(
            {"error": "Failed to restore reel"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class UserReelStatisticsView(APIView):
    """Get reel statistics for a user."""
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'total_reels': {'type': 'integer'},
                    'public_reels': {'type': 'integer'},
                    'private_reels': {'type': 'integer'},
                    'privacy_breakdown': {'type': 'array'},
                    'total_reactions': {'type': 'integer'},
                    'first_reel_date': {'type': 'string', 'format': 'date-time', 'nullable': True}
                }
            }
        },
        description="Get statistics for a user's reels."
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
        else:
            # /users/me/... case
            if not request.user.is_authenticated:
                return Response(
                    {"error": "Authentication required"},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            target_user = request.user
        
        # Privacy: if target user has secret/followers reels, only they can see full stats?
        # For simplicity, we return stats only for public reels if not owner.
        if request.user != target_user:
            # Return only public stats
            total_reels = Reel.objects.filter(user=target_user, privacy='public', is_deleted=False).count()
            public_reels = total_reels
            private_reels = 0
            privacy_breakdown = [{'privacy': 'public', 'count': total_reels}]
            total_reactions = 0
            for reel in Reel.objects.filter(user=target_user, privacy='public', is_deleted=False):
                total_reactions += ReactionService.get_like_count('reel', reel.id)
            first_reel = Reel.objects.filter(user=target_user, privacy='public').order_by('created_at').first()
            first_reel_date = first_reel.created_at if first_reel else None
        else:
            stats = ReelService.get_user_reel_statistics(target_user)
            total_reels = stats['total_reels']
            public_reels = stats['public_reels']
            private_reels = stats['private_reels']
            privacy_breakdown = stats['privacy_breakdown']
            total_reactions = stats['total_reactions']
            first_reel_date = stats['first_reel_date']
        
        return Response({
            'total_reels': total_reels,
            'public_reels': public_reels,
            'private_reels': private_reels,
            'privacy_breakdown': privacy_breakdown,
            'total_reactions': total_reactions,
            'first_reel_date': first_reel_date
        })