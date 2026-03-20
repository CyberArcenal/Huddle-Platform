# feed/views/like_views.py

import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.db import transaction

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from feed.models import Reaction, Post, Comment
from feed.models.reaction import REACTION_TYPES
from feed.serializers.base import ReactionCountSerializer
from feed.serializers.reaction import (
    LikeDisplaySerializer,
    LikeCreateSerializer,
    LikeToggleSerializer,
    ReactionCreateSerializer,
)
from feed.services.reaction import ReactionService
from global_utils.pagination import StandardResultsSetPagination
from users.models import User
from users.serializers.user import UserMinimalSerializer

logger = logging.getLogger(__name__)


# ----- Paginated response serializer for drf-spectacular -----
class PaginatedLikeSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = LikeDisplaySerializer(many=True)


class LikeCheckResponseSerializer(serializers.Serializer):
    has_liked = serializers.BooleanField()
    user_reaction = serializers.ChoiceField(choices=REACTION_TYPES)
    like_count = serializers.IntegerField()
    counts = ReactionCountSerializer()
    content_type = serializers.CharField()
    object_id = serializers.IntegerField()


class ReactionResponseSerializer(serializers.Serializer):
    """Response serializer for ReactionView."""

    reacted = serializers.BooleanField()
    reaction_type = serializers.ChoiceField(choices=REACTION_TYPES, allow_null=True)
    counts = ReactionCountSerializer()


# --------------------------------------------------------------


class LikeListView(APIView):
    """List likes of the authenticated user, or create a new like."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Reaction's"],
        parameters=[
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Filter by content type (post, comment, etc.)",
                required=False,
            ),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: PaginatedLikeSerializer},
        description="List likes created by the authenticated user, optionally filtered by content type.",
    )
    def get(self, request):
        content_type = request.query_params.get("content_type")
        # Get all reactions of type 'like' for the user
        # The service method `get_user_reactions` now supports optional content_type and reaction_type filters
        likes = ReactionService.get_user_reactions(
            user=request.user, content_type=content_type, reaction_type="like"
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(likes, request)
        serializer = LikeDisplaySerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["User Reaction's"],
        request=LikeCreateSerializer,
        responses={201: LikeDisplaySerializer},
        examples=[
            OpenApiExample(
                "Like a post",
                value={"content_type": "post", "object_id": 42},
                request_only=True,
            )
        ],
        description="Create a new like. The user is automatically set to the current user.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = LikeCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            like = serializer.save()
            return Response(
                LikeDisplaySerializer(like, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReactionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Reaction's"],
        request=ReactionCreateSerializer,
        responses={200: ReactionResponseSerializer},
        description="Set any reaction (like, love, haha, etc.) on an object.",
    )
    def post(self, request):
        serializer = ReactionCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {
                    "reacted": result["reacted"],
                    "reaction_type": result["reaction_type"],
                    "counts": result["counts"],
                }
            )
        return Response(serializer.errors, status=400)


class LikeToggleResponseSerializer(serializers.Serializer):
    """Schema for the response of like toggle."""
    liked = serializers.BooleanField(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    message = serializers.CharField(read_only=True)

class LikeToggleView(APIView):
    """Toggle like on an object (add or remove)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Reaction's"],
        request=LikeToggleSerializer,
        responses=LikeToggleResponseSerializer,
        examples=[
            OpenApiExample(
                "Toggle like request",
                value={"content_type": "post", "object_id": 42},
                request_only=True,
            ),
            OpenApiExample(
                "Toggle like response (like created)",
                value={"liked": True, "like_count": 10, "message": "Liked"},
                response_only=True,
            ),
        ],
        description="Toggle like on an object.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = LikeToggleSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            result = serializer.save()  # returns dict with liked, count
            response_data = {
                "liked": result["liked"],
                "like_count": result["count"],
                "message": "Liked" if result["liked"] else "Unliked",
            }
            return Response(LikeToggleResponseSerializer(response_data).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LikeDetailView(APIView):
    """Retrieve or delete a specific like."""

    permission_classes = [IsAuthenticated]

    def get_object(self, like_id):
        # Ensure we only retrieve reactions with reaction_type='like'
        return get_object_or_404(Reaction, id=like_id, reaction_type="like")

    @extend_schema(
        tags=["User Reaction's"],
        responses={200: LikeDisplaySerializer},
        description="Retrieve a specific like (only if owned by current user).",
    )
    def get(self, request, like_id):
        like = self.get_object(like_id)
        if request.user != like.user:
            return Response(
                {"error": "You do not have permission to view this like"},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = LikeDisplaySerializer(like, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["User Reaction's"],
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        description="Delete a like (unlike).",
    )
    @transaction.atomic
    def delete(self, request, like_id):
        like = self.get_object(like_id)
        if request.user != like.user:
            return Response(
                {"error": "You do not have permission to delete this like"},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Get the model name from the ContentType instance
        content_type = like.content_type.model
        success = ReactionService.remove_like(
            user=request.user, content_type=content_type, object_id=like.object_id
        )
        if success:
            return Response({"message": "Like removed successfully"})
        return Response(
            {"error": "Failed to remove like"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ObjectLikesView(APIView):
    """Get all likes for a specific object (post, comment, etc.)."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["User Reaction's"],
        parameters=[
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: PaginatedLikeSerializer},
        description="Get all likes for a specific object.",
    )
    def get(self, request, content_type, object_id):
        # Optional: validate content type via service (will raise ValidationError if invalid)
        # Check privacy if needed (same as before)
        if content_type == "post":
            post = get_object_or_404(Post, id=object_id)
            if not post.privacy == "public" and request.user != post.user:
                return Response(
                    {"error": "You do not have permission to view likes for this post"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif content_type == "comment":
            comment = get_object_or_404(Comment, id=object_id)
            # Assuming Comment has a 'post' relation
            if (
                not comment.post.privacy == "public"
                and request.user != comment.post.user
            ):
                return Response(
                    {
                        "error": "You do not have permission to view likes for this comment"
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        likes = ReactionService.get_reactions_for_object(
            content_type=content_type,
            object_id=object_id,
            reaction_type="like",  # only return likes
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(likes, request)
        serializer = LikeDisplaySerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)


class LikeCheckView(APIView):
    """Check if the authenticated user has liked an object, and get total like count."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Reaction's"],
        responses={200: LikeCheckResponseSerializer},
        description="Check if the authenticated user has liked a specific object, and get total like count.",
    )
    def get(self, request, content_type, object_id):
        # Service will validate content_type
        has_liked = ReactionService.has_liked(
            user=request.user, content_type=content_type, object_id=object_id
        )
        like_count = ReactionService.get_like_count(content_type, object_id)
        reaction_counts = ReactionService.get_reaction_counts(content_type, object_id)
        user_reaction = ReactionService.get_user_reaction(request.user, "post", object_id)
        return Response(
            {
                "has_liked": has_liked,
                "like_count": like_count,
                "user_reaction": user_reaction,
                "counts": reaction_counts,
                "content_type": content_type,
                "object_id": object_id,
            }
        )



class RecentLikersResponseSerializer(serializers.Serializer):
    """Schema for recent likers of a content object."""
    content_type = serializers.CharField(read_only=True)
    object_id = serializers.IntegerField(read_only=True)
    recent_likers = UserMinimalSerializer(many=True, read_only=True)

class RecentLikersView(APIView):
    """Get a list of users who recently liked an object."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["User Reaction's"],
        parameters=[
            OpenApiParameter(name="limit", type=int, required=False),
        ],
        responses=RecentLikersResponseSerializer,
        description="Get a list of users who recently liked an object (limited).",
    )
    def get(self, request, content_type, object_id):
        # Check privacy
        if content_type == "post":
            post = get_object_or_404(Post, id=object_id)
            if not post.privacy == "public" and request.user != post.user:
                return Response(
                    {"error": "You do not have permission to view likers for this post"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        limit = int(request.query_params.get("limit", 10))
        recent_likers = ReactionService.get_recent_reactors(
            content_type=content_type,
            object_id=object_id,
            reaction_type="like",
            limit=limit,
        )

        serializer = UserMinimalSerializer(recent_likers, many=True, context={"request": request})
        response_data = {
            "content_type": content_type,
            "object_id": object_id,
            "recent_likers": serializer.data,
        }
        return Response(RecentLikersResponseSerializer(response_data).data)



class MostLikedContentItemSerializer(serializers.Serializer):
    """Schema for a single most liked content item."""
    type = serializers.CharField(read_only=True)          # "post" or "comment"
    object_id = serializers.IntegerField(read_only=True)
    like_count = serializers.IntegerField(read_only=True)

    # Optional nested serializers depending on content_type
    post = serializers.DictField(read_only=True, required=False)
    comment = serializers.DictField(read_only=True, required=False)


class MostLikedContentResponseSerializer(serializers.Serializer):
    """Schema for the response of most liked content."""
    content_type = serializers.CharField(read_only=True)   # "post" or "comment"
    timeframe_days = serializers.IntegerField(read_only=True)
    results = MostLikedContentItemSerializer(many=True, read_only=True)
    

class MostLikedContentView(APIView):
    """Get the most liked content (posts or comments) within a time period."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["User Reaction's"],
        parameters=[
            OpenApiParameter(name="days", type=int, required=False),
            OpenApiParameter(name="limit", type=int, required=False),
        ],
        responses=MostLikedContentResponseSerializer,
        description="Get the most liked content (posts or comments) within a time period.",
    )
    def get(self, request, content_type):
        if content_type not in ["post", "comment"]:
            return Response(
                {"error": 'Content type must be either "post" or "comment"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        days = int(request.query_params.get("days", 7))
        limit = int(request.query_params.get("limit", 10))

        most_liked = ReactionService.get_most_reacted_content(
            content_type=content_type, days=days, limit=limit, reaction_type="like"
        )

        results = []
        for item in most_liked:
            result = {
                "type": item["type"],
                "object_id": item["object"].id,
                "like_count": item["reaction_count"],
            }
            if content_type == "post":
                from feed.serializers.post import PostFeedSerializer
                result["post"] = PostFeedSerializer(item["object"]).data
            elif content_type == "comment":
                from feed.serializers.comment import CommentMinimalSerializer
                result["comment"] = CommentMinimalSerializer(item["object"]).data
            results.append(result)

        response_data = {
            "content_type": content_type,
            "timeframe_days": days,
            "results": results,
        }
        return Response(MostLikedContentResponseSerializer(response_data).data)



class UserLikeStatisticsSerializer(serializers.Serializer):
    """Schema for like statistics of a user."""

    user_id = serializers.IntegerField(read_only=True)
    total_likes_given = serializers.IntegerField(read_only=True)
    total_likes_received = serializers.IntegerField(read_only=True)

    # breakdown per content type (post, comment, story, reel, etc.)
    type_breakdown = serializers.DictField(
        child=serializers.IntegerField(), read_only=True
    )
    
class UserLikeStatisticsView(APIView):
    """Get like statistics for a user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Reaction's"],
        parameters=[
            OpenApiParameter(name="user_id", type=int, required=False),
        ],
        responses=UserLikeStatisticsSerializer,
        description="Get like statistics for a user (total likes given, breakdown by type, etc.).",
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            if request.user != target_user:
                return Response(
                    {"error": "You can only view your own like statistics"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            target_user = request.user

        stats = ReactionService.get_user_reaction_statistics(target_user)
        # enrich with user_id for schema consistency
        response_data = {
            "user_id": target_user.id,
            **stats
        }
        return Response(UserLikeStatisticsSerializer(response_data).data)


class MutualLikesStatsSerializer(serializers.Serializer):
    """Counts of mutual likes per content type."""
    post = serializers.IntegerField(read_only=True, required=False)
    comment = serializers.IntegerField(read_only=True, required=False)
    story = serializers.IntegerField(read_only=True, required=False)
    reel = serializers.IntegerField(read_only=True, required=False)
    total_mutual_likes = serializers.IntegerField(read_only=True)


class MutualLikeResponse(serializers.Serializer):
    """Response schema for mutual likes between two users."""
    user1_id = serializers.IntegerField()
    user2_id = serializers.IntegerField()
    mutual_likes = MutualLikesStatsSerializer()
    
    
class MutualLikesView(APIView):
    """Get mutual likes (posts/comments both users have liked) between the current user and another user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Reaction's"],
        responses=MutualLikeResponse,
        description="Get mutual likes between the current user and another user.",
    )
    def get(self, request, user_id):
        other_user = get_object_or_404(User, id=user_id)
        mutual = ReactionService.get_mutual_reactions(
            user1=request.user, user2=other_user
        )
        response_data = {
            "user1_id": request.user.id,
            "user2_id": user_id,
            "mutual_likes": mutual,
        }
        return Response(MutualLikeResponse(response_data).data)
