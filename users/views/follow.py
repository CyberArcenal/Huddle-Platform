import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.db.models import Count
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from global_utils.pagination import UsersPagination
from users.serializers.user import UserListSerializer
from users.services.matching import MatchingService
from users.views.user import PaginatedUserListSerializer

from ..services.user_follow import UserFollowService
from ..services.user_activity import UserActivityService
from ..serializers.follow import (
    FollowStatsResponseSerializer,
    FollowStatusResponseSerializer,
    FollowUserResponseSerializer,
    FollowUserSerializer,
    UnfollowUserResponseSerializer,
    UnfollowUserSerializer,
    FollowStatsSerializer,
    FollowerListSerializer,
    FollowingListSerializer,
)
from django.db import transaction
from ..models import User
from rest_framework import serializers

logger = logging.getLogger(__name__)


class FollowUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],
        
        request=FollowUserSerializer,
        responses={201: FollowUserResponseSerializer},
        examples=[
            OpenApiExample("Follow request", value={"following_id": 42}, request_only=True),
            OpenApiExample(
                "Follow response",
                value={
                    "status": True,
                    "message": "Now following johndoe",
                    "follow": {
                        "id": 1,
                        "follower_id": 1,
                        "following_id": 42,
                        "created_at": "2025-03-07T12:34:56Z",
                    },
                },
                response_only=True,
            ),
        ],
        description="Follow another user.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = FollowUserSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid(raise_exception=True):
            try:
                follow = serializer.save()
                return Response(
                    {
                        "status": True,
                        "message": f"Now following {follow.following.username}",
                        "follow": {
                            "id": follow.id,
                            "follower_id": request.user.id,
                            "following_id": follow.following.id,
                            "created_at": follow.created_at,
                        },
                    },
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                logger.error(e)
                return Response({"status": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"status": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class UnfollowUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],
        
        request=UnfollowUserSerializer,
        responses={200: UnfollowUserResponseSerializer},
        examples=[
            OpenApiExample("Unfollow request", value={"following_id": 42}, request_only=True),
            OpenApiExample(
                "Unfollow response",
                value={"status": True, "message": "Unfollowed successfully"},
                response_only=True,
            ),
        ],
        description="Unfollow a user.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = UnfollowUserSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid(raise_exception=True):
            try:
                success = serializer.unfollow()
                if success:
                    return Response(
                        {"status": True, "message": "Unfollowed successfully"},
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {"status": False, "error": "Failed to unfollow"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception as e:
                return Response({"status": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class FollowStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],
        
        responses={200: FollowStatusResponseSerializer},
        description="Check if the current user is following another user.",
    )
    def get(self, request, user_id):
        try:
            target_user = get_object_or_404(User, id=user_id)
            is_following = UserFollowService.is_following(
                follower=request.user, following=target_user
            )
            return Response(
                {
                    "is_following": is_following,
                    "user_id": user_id,
                    "username": target_user.username,
                }
            )
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FollowStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],
        
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (optional, defaults to current)",
                required=False,
            ),
        ],
        responses={200: FollowStatsResponseSerializer},
        description="Get follower and following counts for a user.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                user = get_object_or_404(User, id=user_id)
            else:
                user = request.user

            followers_count = UserFollowService.get_follower_count(user)
            following_count = UserFollowService.get_following_count(user)
            mutual_followers_count = 0  # placeholder

            stats_data = {
                "followers_count": followers_count,
                "following_count": following_count,
                "mutual_followers_count": mutual_followers_count,
            }
            stats_serializer = FollowStatsSerializer(stats_data)

            return Response(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "stats": stats_serializer.data,
                }
            )
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FollowersListView(APIView):
    """View for listing followers"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],
        
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (optional, defaults to current)",
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
        responses={200: PaginatedUserListSerializer},
        description="List followers of a user (paginated).",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                user = get_object_or_404(User, id=user_id)
            else:
                user = request.user

            followers = UserFollowService.get_followers(user)

            paginator = UsersPagination()
            page = paginator.paginate_queryset(followers, request)
            serializer = UserListSerializer(
                page, many=True, context={"request": request, "following": user}
            )
            return paginator.get_paginated_response(serializer.data)

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.debug(e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FollowingListView(APIView):
    """View for listing users being followed"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],
        
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (optional, defaults to current)",
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
        responses={200: PaginatedUserListSerializer},
        description="List users followed by a user (paginated).",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                user = get_object_or_404(User, id=user_id)
            else:
                user = request.user

            following = UserFollowService.get_following(user)

            paginator = UsersPagination()
            page = paginator.paginate_queryset(following, request)
            serializer = UserListSerializer(
                page, many=True, context={"request": request, "follower": user}
            )
            return paginator.get_paginated_response(serializer.data)

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MutualFollowsView(APIView):
    """View for getting mutual follows between users"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],
        
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
        responses={200: PaginatedUserListSerializer},
        description="Get mutual followers between the current user and another user.",
    )
    def get(self, request, user_id):
        try:
            other_user = get_object_or_404(User, id=user_id)

            mutual_follows = UserFollowService.get_mutual_follows(
                user1=request.user, user2=other_user
            )

            paginator = UsersPagination()
            page = paginator.paginate_queryset(mutual_follows, request)

            serializer = UserListSerializer(
                page, many=True, context={"request": request}
            )

            # Return standard paginated response matching PaginatedUserListSerializer
            return paginator.get_paginated_response(serializer.data)

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# users/views/follow.py (updated part)

from users.services.matching import MatchingService
from users.serializers.matching import UserMutualCountSerializer


class SuggestedUsersView(APIView):
    """View for getting suggested users to follow based on mutual connections."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],
        
        parameters=[
            OpenApiParameter(
                name="limit", type=int, description="Number of suggestions", required=False
            ),
            OpenApiParameter(
                name="offset", type=int, description="Offset for pagination", required=False
            ),
            OpenApiParameter(
                name="min_mutual", type=int, description="Minimum number of mutual friends", required=False
            ),
        ],
        responses={200: UserMutualCountSerializer(many=True)},
        description="Get suggested users based on friends of friends (mutual connections).",
    )
    def get(self, request):
        limit = int(request.query_params.get('limit', 10))
        offset = int(request.query_params.get('offset', 0))
        min_mutual = int(request.query_params.get('min_mutual', 1))

        suggestions = MatchingService.get_suggested_users(
            user=request.user,
            limit=limit,
            offset=offset,
            min_mutual=min_mutual
        )

        # suggestions is already a list of dicts with 'user' and 'mutual_count'
        serializer = UserMutualCountSerializer(suggestions, many=True, context={'request': request})
        return Response(serializer.data)


class MutualFriendsView(APIView):
    """View for getting mutual friends of the current user (users who follow you back)"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],

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
        responses={200: PaginatedUserListSerializer},
        description="Get paginated list of users who are mutual followers (you follow them and they follow you).",
    )
    def get(self, request):
        try:
            following = UserFollowService.get_following(request.user)
            followers = UserFollowService.get_followers(request.user)

            mutual_friends = following.filter(id__in=followers.values("id"))

            paginator = UsersPagination()
            page = paginator.paginate_queryset(mutual_friends, request)
            serializer = UserListSerializer(
                page, many=True, context={"request": request, "follower": request.user}
            )
            return paginator.get_paginated_response(serializer.data)

        except Exception as e:
            logger.error(e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PopularUsersView(APIView):
    """View for getting popular users (most followed) with pagination"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow Views"],
        
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
        responses={200: PaginatedUserListSerializer},
        description="Get paginated list of users ordered by follower count (descending).",
    )
    def get(self, request):
        try:
            popular_users = User.objects.annotate(
                follower_count=Count("followers")
            ).order_by("-follower_count")

            paginator = UsersPagination()
            page = paginator.paginate_queryset(popular_users, request)
            serializer = UserListSerializer(
                page, many=True, context={"request": request, "follower": request.user}
            )
            return paginator.get_paginated_response(serializer.data)

        except Exception as e:
            logger.error(e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
