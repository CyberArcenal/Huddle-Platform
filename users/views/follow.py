# users/views/follow.py
import logging
import traceback

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from django.db.models import Count
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from global_utils.pagination import StandardResultsSetPagination, UsersPagination
from users.serializers.user.base import UserListSerializer
from dating.services.matching import MatchingService

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

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated users
# ----------------------------------------------------------------------
def wrap_paginated_users(paginator, page, request, context_extra=None):
    """
    Build paginated data dict for user lists.
    """
    serializer = UserListSerializer(
        page, many=True, context={"request": request, **(context_extra or {})}
    )
    data = {
        "page": paginator.page.number,
        "hasNext": paginator.page.has_next(),
        "hasPrev": paginator.page.has_previous(),
        "count": paginator.page.paginator.count,
        "next": paginator.get_next_link(),
        "previous": paginator.get_previous_link(),
        "results": serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------


class FollowResponseData(serializers.Serializer):
    id = serializers.IntegerField()
    follower_id = serializers.IntegerField()
    following_id = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class FollowResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = FollowResponseData()


class UnfollowResponseData(serializers.Serializer):
    message = serializers.CharField()


class UnfollowResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UnfollowResponseData()


class FollowStatusResponseData(serializers.Serializer):
    is_following = serializers.BooleanField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()


class FollowStatusResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = FollowStatusResponseData()


class FollowStatsResponseData(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    stats = FollowStatsSerializer()


class FollowStatsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = FollowStatsResponseData()


class PaginatedUserListData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserListSerializer(many=True)


class FollowersListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedUserListData()


class FollowingListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedUserListData()


class MutualFollowsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedUserListData()


class MutualFriendsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedUserListData()


class PopularUsersResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedUserListData()


class SuggestedUsersResponseData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = serializers.ListField(
        child=serializers.DictField()
    )  # UserMutualCountSerializer


class SuggestedUsersResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SuggestedUsersResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------


class FollowUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
        request=FollowUserSerializer,
        responses={201: FollowResponseSerializer},
        examples=[
            OpenApiExample(
                "Follow request", value={"following_id": 42}, request_only=True
            ),
            OpenApiExample(
                "Follow response",
                value={
                    "status": True,
                    "message": "Now following johndoe",
                    "data": {
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
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            follow = serializer.save()
            data = {
                "id": follow.id,
                "follower_id": request.user.id,
                "following_id": follow.following.id,
                "created_at": follow.created_at,
            }
            return Response(
                {
                    "status": True,
                    "message": f"Now following {follow.following.username}",
                    "data": data,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            traceback.print_exc()
            logger.exception("FollowUserView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class UnfollowUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
        request=UnfollowUserSerializer,
        responses={200: UnfollowResponseSerializer},
        examples=[
            OpenApiExample(
                "Unfollow request", value={"following_id": 42}, request_only=True
            ),
            OpenApiExample(
                "Unfollow response",
                value={
                    "status": True,
                    "message": "Unfollowed successfully",
                    "data": {"message": "Unfollowed successfully"},
                },
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
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            success = serializer.unfollow()
            if success:
                return Response(
                    {
                        "status": True,
                        "message": "Unfollowed successfully",
                        "data": {"message": "Unfollowed successfully"},
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "status": False,
                        "message": "Failed to unfollow",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            traceback.print_exc()
            logger.exception("UnfollowUserView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class FollowStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
        responses={200: FollowStatusResponseSerializer},
        description="Check if the current user is following another user.",
    )
    def get(self, request, user_id):
        try:
            target_user = get_object_or_404(User, id=user_id)
            is_following = UserFollowService.is_following(
                follower=request.user, following=target_user
            )
            data = {
                "is_following": is_following,
                "user_id": user_id,
                "username": target_user.username,
            }
            return Response(
                {
                    "status": True,
                    "message": "Follow status retrieved.",
                    "data": data,
                }
            )
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            traceback.print_exc()
            logger.exception("FollowStatusView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FollowStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
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

            stats_data = {
                "followers_count": followers_count,
                "following_count": following_count,
                "mutual_followers_count": 0,  # placeholder
            }
            stats_serializer = FollowStatsSerializer(stats_data)

            data = {
                "user_id": user.id,
                "username": user.username,
                "stats": stats_serializer.data,
            }
            return Response(
                {
                    "status": True,
                    "message": "Follow stats retrieved.",
                    "data": data,
                }
            )
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            traceback.print_exc()
            logger.exception("FollowStatsView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FollowersListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
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
        responses={200: FollowersListResponseSerializer},
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
            paginated_data = wrap_paginated_users(
                paginator, page, request, context_extra={"following": user}
            )

            return Response(
                {
                    "status": True,
                    "message": "Followers retrieved.",
                    "data": paginated_data,
                }
            )
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            traceback.print_exc()
            logger.exception("FollowersListView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FollowingListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
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
        responses={200: FollowingListResponseSerializer},
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
            paginated_data = wrap_paginated_users(
                paginator, page, request, context_extra={"follower": user}
            )

            return Response(
                {
                    "status": True,
                    "message": "Following retrieved.",
                    "data": paginated_data,
                }
            )
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            traceback.print_exc()
            logger.exception("FollowingListView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MutualFollowsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
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
        responses={200: MutualFollowsResponseSerializer},
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
            paginated_data = wrap_paginated_users(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Mutual follows retrieved.",
                    "data": paginated_data,
                }
            )
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            traceback.print_exc()
            logger.exception("MutualFollowsView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SuggestedUsersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
        parameters=[
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Number of results per page",
                required=False,
            ),
            OpenApiParameter(
                name="min_mutual",
                type=int,
                description="Minimum number of mutual friends",
                required=False,
            ),
        ],
        responses={200: SuggestedUsersResponseSerializer},
        description="Get suggested users based on friends of friends (mutual connections).",
    )
    def get(self, request):
        try:
            min_mutual = int(request.query_params.get("min_mutual", 1))
            suggestions = MatchingService.get_suggested_users(
                user=request.user, limit=100, min_mutual=min_mutual
            )
            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(suggestions, request, view=self)
            from users.serializers.matching import UserMutualCountSerializer

            serializer = UserMutualCountSerializer(
                page, many=True, context={"request": request}
            )

            # Build paginated data
            data = {
                "page": paginator.page.number,
                "hasNext": paginator.page.has_next(),
                "hasPrev": paginator.page.has_previous(),
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": serializer.data,
            }
            return Response(
                {
                    "status": True,
                    "message": "Suggested users retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            traceback.print_exc()
            logger.exception("SuggestedUsersView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MutualFriendsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
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
        responses={200: MutualFriendsResponseSerializer},
        description="Get paginated list of users who are mutual followers (you follow them and they follow you).",
    )
    def get(self, request):
        try:
            following = UserFollowService.get_following(request.user)
            followers = UserFollowService.get_followers(request.user)
            mutual_friends = following.filter(id__in=followers.values("id"))

            paginator = UsersPagination()
            page = paginator.paginate_queryset(mutual_friends, request)
            paginated_data = wrap_paginated_users(
                paginator, page, request, context_extra={"follower": request.user}
            )

            return Response(
                {
                    "status": True,
                    "message": "Mutual friends retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            traceback.print_exc()
            logger.exception("MutualFriendsView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PopularUsersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Follow"],
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
        responses={200: PopularUsersResponseSerializer},
        description="Get paginated list of users ordered by follower count (descending).",
    )
    def get(self, request):
        try:
            popular_users = User.objects.annotate(
                follower_count=Count("followers")
            ).order_by("-follower_count")

            paginator = UsersPagination()
            page = paginator.paginate_queryset(popular_users, request)
            paginated_data = wrap_paginated_users(
                paginator, page, request, context_extra={"follower": request.user}
            )

            return Response(
                {
                    "status": True,
                    "message": "Popular users retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            traceback.print_exc()
            logger.exception("PopularUsersView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
