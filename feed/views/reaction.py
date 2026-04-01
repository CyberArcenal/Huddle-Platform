# feed/views/reaction.py

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
    ReactionDisplaySerializer,
    LikeCreateSerializer,
    LikeToggleSerializer,
    ReactionCreateSerializer,
)
from feed.services.reaction import ReactionService
from feed.utils.reaction import can_view_content
from global_utils.pagination import StandardResultsSetPagination
from users.models import User
from users.serializers.user.minimal import UserMinimalSerializer

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_data(paginator, page, request, serializer_class):
    """
    Construct a paginated data dict that matches the paginated response structure.
    """
    serializer = serializer_class(page, many=True, context={'request': request})
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
# Response serializers
# ----------------------------------------------------------------------

class PaginatedReactionSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ReactionDisplaySerializer(many=True)


class LikeListResponseData(serializers.Serializer):
    pagination = PaginatedReactionSerializer()


class LikeListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LikeListResponseData(allow_null=True)


class LikeCreateResponseData(serializers.Serializer):
    reaction = ReactionDisplaySerializer()


class LikeCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LikeCreateResponseData(allow_null=True)


class ReactionResponseData(serializers.Serializer):
    object_id = serializers.IntegerField()
    content_type = serializers.CharField()
    reacted = serializers.BooleanField()
    reaction_type = serializers.ChoiceField(choices=REACTION_TYPES, allow_null=True)
    reaction_count = serializers.IntegerField()
    counts = ReactionCountSerializer()


class ReactionResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ReactionResponseData()


class LikeToggleResponseData(serializers.Serializer):
    liked = serializers.BooleanField()
    like_count = serializers.IntegerField()


class LikeToggleResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LikeToggleResponseData()


class LikeDetailResponseData(serializers.Serializer):
    reaction = ReactionDisplaySerializer()


class LikeDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LikeDetailResponseData(allow_null=True)


class LikeDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class ObjectLikesResponseData(serializers.Serializer):
    pagination = PaginatedReactionSerializer()


class ObjectLikesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ObjectLikesResponseData(allow_null=True)


class LikeCheckResponseData(serializers.Serializer):
    has_liked = serializers.BooleanField()
    like_count = serializers.IntegerField()
    user_reaction = serializers.ChoiceField(choices=REACTION_TYPES, allow_null=True)
    counts = ReactionCountSerializer()
    content_type = serializers.CharField()
    object_id = serializers.IntegerField()


class LikeCheckResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LikeCheckResponseData()


class RecentLikersResponseData(serializers.Serializer):
    content_type = serializers.CharField()
    object_id = serializers.IntegerField()
    recent_likers = UserMinimalSerializer(many=True)


class RecentLikersResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = RecentLikersResponseData()


class MostLikedContentItemSerializer(serializers.Serializer):
    type = serializers.CharField()
    object_id = serializers.IntegerField()
    like_count = serializers.IntegerField()
    post = serializers.DictField(required=False, allow_null=True)
    comment = serializers.DictField(required=False, allow_null=True)


class MostLikedContentResponseData(serializers.Serializer):
    content_type = serializers.CharField()
    timeframe_days = serializers.IntegerField()
    results = MostLikedContentItemSerializer(many=True)


class MostLikedContentResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MostLikedContentResponseData()


class UserLikeStatisticsResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()
    total_likes_given = serializers.IntegerField()
    total_likes_received = serializers.IntegerField()
    type_breakdown = serializers.DictField(child=serializers.IntegerField())


class UserLikeStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserLikeStatisticsResponseData()


class MutualLikesStatsSerializer(serializers.Serializer):
    post = serializers.IntegerField(required=False)
    comment = serializers.IntegerField(required=False)
    story = serializers.IntegerField(required=False)
    reel = serializers.IntegerField(required=False)
    total_mutual_likes = serializers.IntegerField()


class MutualLikesResponseData(serializers.Serializer):
    user1_id = serializers.IntegerField()
    user2_id = serializers.IntegerField()
    mutual_likes = MutualLikesStatsSerializer()


class MutualLikesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MutualLikesResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class LikeListView(APIView):
    """List likes of the authenticated user, or create a new like."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Reaction's"],
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
        responses={200: LikeListResponseSerializer},
        description="List likes created by the authenticated user, optionally filtered by content type.",
    )
    def get(self, request):
        content_type = request.query_params.get("content_type")
        try:
            likes = ReactionService.get_user_reactions(
                user=request.user, content_type=content_type, reaction_type="like"
            )
            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(likes, request)
            paginated_data = wrap_paginated_data(paginator, page, request, ReactionDisplaySerializer)

            return Response(
                {
                    "status": True,
                    "message": "Likes retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )
        except Exception as e:
            logger.exception("Error listing likes")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Reaction's"],
        request=LikeCreateSerializer,
        responses={201: LikeCreateResponseSerializer},
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
            data = ReactionDisplaySerializer(like, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Like created successfully.",
                    "data": {"reaction": data},
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {
                "status": False,
                "message": "Validation error.",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class ReactionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Reaction's"],
        request=ReactionCreateSerializer,
        responses={200: ReactionResponseSerializer},
        description="Set any reaction (like, love, haha, etc.) on an object.",
    )
    @transaction.atomic
    def post(self, request):
        logger.debug(request.data)
        serializer = ReactionCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid(raise_exception=True):
            result = serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Reaction processed.",
                    "data": result,
                }
            )
        return Response(
            {
                "status": False,
                "message": "Validation error.",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class LikeToggleView(APIView):
    """Toggle like on an object (add or remove)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Reaction's"],
        request=LikeToggleSerializer,
        responses={200: LikeToggleResponseSerializer},
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
            return Response(
                {
                    "status": True,
                    "message": "Liked" if result["liked"] else "Unliked",
                    "data": {
                        "liked": result["liked"],
                        "like_count": result["count"],
                    },
                }
            )
        return Response(
            {
                "status": False,
                "message": "Validation error.",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class LikeDetailView(APIView):
    """Retrieve or delete a specific like."""

    permission_classes = [IsAuthenticated]

    def get_object(self, like_id):
        return get_object_or_404(Reaction, id=like_id, reaction_type="like")

    @extend_schema(
        tags=["Reaction's"],
        responses={200: LikeDetailResponseSerializer},
        description="Retrieve a specific like (only if owned by current user).",
    )
    def get(self, request, like_id):
        like = self.get_object(like_id)
        if request.user != like.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view this like",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        data = ReactionDisplaySerializer(like, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Like retrieved.",
                "data": {"reaction": data},
            }
        )

    @extend_schema(
        tags=["Reaction's"],
        responses={200: LikeDeleteResponseSerializer},
        description="Delete a like (unlike).",
    )
    @transaction.atomic
    def delete(self, request, like_id):
        like = self.get_object(like_id)
        if request.user != like.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to delete this like",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        content_type = like.content_type.model
        success = ReactionService.remove_like(
            user=request.user, content_type=content_type, object_id=like.object_id
        )
        if success:
            return Response(
                {
                    "status": True,
                    "message": "Like removed successfully",
                    "data": None,
                }
            )
        return Response(
            {
                "status": False,
                "message": "Failed to remove like",
                "data": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ObjectLikesView(APIView):
    """Get all likes for a specific object (post, comment, etc.)."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Reaction's"],
        parameters=[
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: ObjectLikesResponseSerializer},
        description="Get all likes for a specific object.",
    )
    def get(self, request, content_type, object_id):
        if not can_view_content(request.user, content_type, object_id):
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view likes for this object",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        likes = ReactionService.get_reactions_for_object(
            content_type=content_type,
            object_id=object_id,
            reaction_type="like",
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(likes, request)
        paginated_data = wrap_paginated_data(paginator, page, request, ReactionDisplaySerializer)

        return Response(
            {
                "status": True,
                "message": "Likes retrieved.",
                "data": {"pagination": paginated_data},
            }
        )


class LikeCheckView(APIView):
    """Check if the authenticated user has liked an object, and get total like count."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Reaction's"],
        responses={200: LikeCheckResponseSerializer},
        description="Check if the authenticated user has liked a specific object, and get total like count.",
    )
    def get(self, request, content_type, object_id):
        if not can_view_content(request.user, content_type, object_id):
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view like status",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        has_liked = ReactionService.has_liked(
            user=request.user, content_type=content_type, object_id=object_id
        )
        like_count = ReactionService.get_like_count(content_type, object_id)
        reaction_counts = ReactionService.get_reaction_counts(content_type, object_id)
        user_reaction = ReactionService.get_user_reaction(
            request.user, content_type, object_id
        )

        data = {
            "has_liked": has_liked,
            "like_count": like_count,
            "user_reaction": user_reaction,
            "counts": reaction_counts,
            "content_type": content_type,
            "object_id": object_id,
        }
        return Response(
            {
                "status": True,
                "message": "Like status retrieved.",
                "data": data,
            }
        )


class RecentLikersView(APIView):
    """Get a list of users who recently liked an object."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Reaction's"],
        parameters=[
            OpenApiParameter(name="limit", type=int, required=False),
        ],
        responses={200: RecentLikersResponseSerializer},
        description="Get a list of users who recently liked an object (limited).",
    )
    def get(self, request, content_type, object_id):
        if not can_view_content(request.user, content_type, object_id):
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view recent likers",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        limit = int(request.query_params.get("limit", 10))
        recent_likers = ReactionService.get_recent_reactors(
            content_type=content_type,
            object_id=object_id,
            reaction_type="like",
            limit=limit,
        )
        serializer = UserMinimalSerializer(
            recent_likers, many=True, context={"request": request}
        )
        data = {
            "content_type": content_type,
            "object_id": object_id,
            "recent_likers": serializer.data,
        }
        return Response(
            {
                "status": True,
                "message": "Recent likers retrieved.",
                "data": data,
            }
        )


class MostLikedContentView(APIView):
    """Get the most liked content (posts or comments) within a time period."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Reaction's"],
        parameters=[
            OpenApiParameter(name="days", type=int, required=False),
            OpenApiParameter(name="limit", type=int, required=False),
        ],
        responses={200: MostLikedContentResponseSerializer},
        description="Get the most liked content (posts or comments) within a time period.",
    )
    def get(self, request, content_type):
        if content_type not in ["post", "comment"]:
            return Response(
                {
                    "status": False,
                    "message": 'Content type must be either "post" or "comment"',
                    "data": None,
                },
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
                result["comment"] = None
            elif content_type == "comment":
                from feed.serializers.comment import CommentMinimalSerializer
                result["comment"] = CommentMinimalSerializer(item["object"]).data
                result["post"] = None
            results.append(result)

        data = {
            "content_type": content_type,
            "timeframe_days": days,
            "results": results,
        }
        return Response(
            {
                "status": True,
                "message": "Most liked content retrieved.",
                "data": data,
            }
        )


class UserLikeStatisticsView(APIView):
    """Get like statistics for a user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Reaction's"],
        parameters=[
            OpenApiParameter(name="user_id", type=int, required=False),
        ],
        responses={200: UserLikeStatisticsResponseSerializer},
        description="Get like statistics for a user (total likes given, breakdown by type, etc.).",
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            if request.user != target_user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only view your own like statistics",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            target_user = request.user

        stats = ReactionService.get_user_reaction_statistics(target_user)
        data = {"user_id": target_user.id, **stats}
        return Response(
            {
                "status": True,
                "message": "User statistics retrieved.",
                "data": data,
            }
        )


class MutualLikesView(APIView):
    """Get mutual likes (posts/comments both users have liked) between the current user and another user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Reaction's"],
        responses={200: MutualLikesResponseSerializer},
        description="Get mutual likes between the current user and another user.",
    )
    def get(self, request, user_id):
        other_user = get_object_or_404(User, id=user_id)
        mutual = ReactionService.get_mutual_reactions(
            user1=request.user, user2=other_user
        )
        data = {
            "user1_id": request.user.id,
            "user2_id": user_id,
            "mutual_likes": mutual,
        }
        return Response(
            {
                "status": True,
                "message": "Mutual likes retrieved.",
                "data": data,
            }
        )