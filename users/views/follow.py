from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import UsersPagination

from ..services.user_follow import UserFollowService
from ..services.user_activity import UserActivityService
from ..serializers.follow import (
    FollowUserSerializer,
    UnfollowUserSerializer,
    FollowStatsSerializer,
    FollowerListSerializer,
    FollowingListSerializer,
)
from django.db import transaction
from ..models import User
from rest_framework import serializers
from ..serializers.follow import FollowerListSerializer, FollowingListSerializer


class PaginatedFollowerListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = FollowerListSerializer(many=True)


class PaginatedFollowingListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = FollowingListSerializer(many=True)


class FollowUserView(APIView):
    """View for following a user"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=FollowUserSerializer,
        responses={201: {"type": "object"}},
        examples=[
            OpenApiExample("Follow request", value={"user_id": 42}, request_only=True),
            OpenApiExample(
                "Follow response",
                value={
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

        if serializer.is_valid():
            try:
                follow = serializer.save()

                UserActivityService.log_activity(
                    user=request.user,
                    action="follow",
                    description=f"Started following user ID: {follow.following.id}",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                    metadata={"following_id": follow.following.id},
                )

                return Response(
                    {
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
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class UnfollowUserView(APIView):
    """View for unfollowing a user"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=UnfollowUserSerializer,
        responses={200: {"type": "object"}},
        examples=[
            OpenApiExample(
                "Unfollow request", value={"user_id": 42}, request_only=True
            ),
            OpenApiExample(
                "Unfollow response",
                value={"message": "Unfollowed successfully"},
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

        if serializer.is_valid():
            try:
                success = serializer.unfollow()

                if success:
                    return Response(
                        {"message": "Unfollowed successfully"},
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {"error": "Failed to unfollow"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class FollowStatusView(APIView):
    """View for checking follow status"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}},
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
    """View for getting follow statistics"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (optional, defaults to current)",
                required=False,
            ),
        ],
        responses={200: FollowStatsSerializer},
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

            if user == request.user:
                mutual_followers_count = 0  # placeholder
            else:
                mutual_followers_count = 0

            stats_data = {
                "followers_count": followers_count,
                "following_count": following_count,
                "mutual_followers_count": mutual_followers_count,
            }

            serializer = FollowStatsSerializer(stats_data)

            return Response(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "stats": serializer.data,
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
        responses={200: PaginatedFollowerListSerializer},
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
            serializer = FollowerListSerializer(
                page, many=True, context={"request": request, "following": user}
            )
            return paginator.get_paginated_response(serializer.data)

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FollowingListView(APIView):
    """View for listing users being followed"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
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
        responses={200: PaginatedFollowingListSerializer},
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
            serializer = FollowingListSerializer(
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
        responses={200: {"type": "object"}},
        description="Get mutual followers between the current user and another user.",
    )
    def get(self, request, user_id):
        try:
            other_user = get_object_or_404(User, id=user_id)

            mutual_follows = UserFollowService.get_mutual_follows(
                user1=request.user, user2=other_user
            )

            from ..serializers.user import UserListSerializer

            serializer = UserListSerializer(
                mutual_follows, many=True, context={"request": request}
            )

            return Response(
                {
                    "user1_id": request.user.id,
                    "user2_id": other_user.id,
                    "count": len(mutual_follows),
                    "mutual_follows": serializer.data,
                }
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SuggestedUsersView(APIView):
    """View for getting suggested users to follow"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of suggestions (default 10)",
                required=False,
            ),
        ],
        responses={200: {"type": "object"}},
        description="Get suggested users to follow based on mutual connections.",
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 10))
            suggested_users = UserFollowService.get_suggested_users(
                user=request.user, limit=limit
            )

            from ..serializers.user import UserListSerializer

            serializer = UserListSerializer(
                suggested_users, many=True, context={"request": request}
            )

            return Response(
                {"count": len(suggested_users), "suggested_users": serializer.data}
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
