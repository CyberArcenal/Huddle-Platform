# dating/views/friendship.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from users.models import User
from users.models.friendship import Friendship
from users.serializers.friendship import (
    FriendRemoveSerializer,
    FriendshipCreateSerializer,
    FriendshipDetailSerializer,
    FriendshipMinimalSerializer,
    TagUpdateSerializer,
)
from users.serializers.user.minimal import UserMinimalSerializer
from users.services.friendship import FriendshipService

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to build paginated data
# ----------------------------------------------------------------------
def build_paginated_friendship_data(request, queryset, serializer_class, limit, offset):
    """
    Build paginated data dict for friendship lists.
    """
    total = queryset.count()
    items = queryset[offset : offset + limit]
    serializer = serializer_class(items, many=True, context={"request": request})

    base_url = request.build_absolute_uri(request.path)
    next_url = (
        f"{base_url}?limit={limit}&offset={offset + limit}"
        if offset + limit < total
        else None
    )
    prev_url = (
        f"{base_url}?limit={limit}&offset={max(0, offset - limit)}"
        if offset > 0
        else None
    )

    return {
        "count": total,
        "next": next_url,
        "previous": prev_url,
        "results": serializer.data,
    }


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------


class FriendshipDetailResponseData(serializers.Serializer):
    friendship = FriendshipDetailSerializer()


class FriendshipDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = FriendshipDetailResponseData()


class PaginatedFriendsData(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = FriendshipMinimalSerializer(many=True)


class PaginatedFriendsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedFriendsData()


class PaginatedPendingRequestsData(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = FriendshipMinimalSerializer(many=True)


class PaginatedPendingRequestsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedPendingRequestsData()


class FriendRemoveResponseData(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()


class FriendRemoveResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = FriendRemoveResponseData()


class TagUpdateResponseData(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()


class TagUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TagUpdateResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------


class FriendRequestSendView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Friendships"],
        request=FriendshipCreateSerializer,
        responses={201: FriendshipDetailResponseSerializer},
        description="Send a friend request to another user.",
        examples=[
            OpenApiExample(
                "Example request",
                value={"to_user": 123, "tag": "normal"},
                request_only=True,
            ),
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "Friend request sent.",
                    "data": {
                        "friendship": {
                            "id": 1,
                            "user": {
                                "id": 1,
                                "username": "alice",
                                "first_name": "Alice",
                                "last_name": "Smith",
                                "avatar": None,
                            },
                            "friend": {
                                "id": 123,
                                "username": "bob",
                                "first_name": "Bob",
                                "last_name": "Johnson",
                                "avatar": None,
                            },
                            "status": "pending",
                            "tag": "normal",
                            "created_at": "2025-03-27T12:00:00Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = FriendshipCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        friendship = serializer.save()
        output_serializer = FriendshipDetailSerializer(
            friendship, context={"request": request}
        )
        return Response(
            {
                "status": True,
                "message": "Friend request sent.",
                "data": {"friendship": output_serializer.data},
            },
            status=status.HTTP_201_CREATED,
        )


class FriendRequestAcceptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Friendships"],
        responses={200: FriendshipDetailResponseSerializer},
        description="Accept a pending friend request. Only the recipient can accept.",
        examples=[
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "Friend request accepted.",
                    "data": {
                        "friendship": {
                            "id": 1,
                            "user": {
                                "id": 1,
                                "username": "alice",
                                "first_name": "Alice",
                                "last_name": "Smith",
                                "avatar": None,
                            },
                            "friend": {
                                "id": 123,
                                "username": "bob",
                                "first_name": "Bob",
                                "last_name": "Johnson",
                                "avatar": None,
                            },
                            "status": "accepted",
                            "tag": "normal",
                            "created_at": "2025-03-27T12:00:00Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, pk):
        try:
            friendship = get_object_or_404(Friendship, pk=pk)
            if friendship.to_user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "Only the recipient can accept this request.",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if friendship.status != "pending":
                return Response(
                    {
                        "status": False,
                        "message": "Only pending requests can be accepted.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            updated = FriendshipService.accept_request(friendship)
            output_serializer = FriendshipDetailSerializer(
                updated, context={"request": request}
            )
            return Response(
                {
                    "status": True,
                    "message": "Friend request accepted.",
                    "data": {"friendship": output_serializer.data},
                }
            )
        except Exception as e:
            logger.exception("Error accepting friend request %s", pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FriendRequestDeclineView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Friendships"],
        responses={200: FriendshipDetailResponseSerializer},
        description="Decline a pending friend request. Only the recipient can decline.",
        examples=[
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "Friend request declined.",
                    "data": {
                        "friendship": {
                            "id": 1,
                            "user": {
                                "id": 1,
                                "username": "alice",
                                "first_name": "Alice",
                                "last_name": "Smith",
                                "avatar": None,
                            },
                            "friend": {
                                "id": 123,
                                "username": "bob",
                                "first_name": "Bob",
                                "last_name": "Johnson",
                                "avatar": None,
                            },
                            "status": "declined",
                            "tag": "normal",
                            "created_at": "2025-03-27T12:00:00Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, pk):
        try:
            friendship = get_object_or_404(Friendship, pk=pk)
            if friendship.to_user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "Only the recipient can decline this request.",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if friendship.status != "pending":
                return Response(
                    {
                        "status": False,
                        "message": "Only pending requests can be declined.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            updated = FriendshipService.decline_request(friendship)
            output_serializer = FriendshipDetailSerializer(
                updated, context={"request": request}
            )
            return Response(
                {
                    "status": True,
                    "message": "Friend request declined.",
                    "data": {"friendship": output_serializer.data},
                }
            )
        except Exception as e:
            logger.exception("Error declining friend request %s", pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FriendsListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Friendships"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of results per page",
                required=False,
            ),
            OpenApiParameter(
                name="offset",
                type=int,
                description="Offset for pagination",
                required=False,
            ),
        ],
        responses={200: PaginatedFriendsResponseSerializer},
        description="Get paginated list of accepted friends.",
        examples=[
            OpenApiExample(
                "Paginated response",
                value={
                    "status": True,
                    "message": "Friends list retrieved.",
                    "data": {
                        "count": 2,
                        "next": "http://example.com/friends/?limit=10&offset=10",
                        "previous": None,
                        "results": [
                            {
                                "id": 1,
                                "friend": {
                                    "id": 123,
                                    "username": "bob",
                                    "first_name": "Bob",
                                    "last_name": "Johnson",
                                    "avatar": None,
                                },
                                "tag": "normal",
                                "status": "accepted",
                                "created_at": "2025-03-27T12:00:00Z",
                            }
                        ],
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 20))
            offset = int(request.query_params.get("offset", 0))

            queryset = Friendship.objects.filter(
                from_user=request.user, status="accepted"
            ).select_related("to_user")

            data = build_paginated_friendship_data(
                request, queryset, FriendshipMinimalSerializer, limit, offset
            )
            return Response(
                {
                    "status": True,
                    "message": "Friends list retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error listing friends")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PendingRequestsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Friendships"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of results per page",
                required=False,
            ),
            OpenApiParameter(
                name="offset",
                type=int,
                description="Offset for pagination",
                required=False,
            ),
        ],
        responses={200: PaginatedPendingRequestsResponseSerializer},
        description="Get paginated list of pending friend requests received.",
        examples=[
            OpenApiExample(
                "Paginated response",
                value={
                    "status": True,
                    "message": "Pending requests retrieved.",
                    "data": {
                        "count": 2,
                        "next": "http://example.com/friends/requests/pending/?limit=10&offset=10",
                        "previous": None,
                        "results": [
                            {
                                "id": 1,
                                "friend": {
                                    "id": 123,
                                    "username": "bob",
                                    "first_name": "Bob",
                                    "last_name": "Johnson",
                                    "avatar": None,
                                },
                                "tag": "normal",
                                "status": "pending",
                                "created_at": "2025-03-27T12:00:00Z",
                            }
                        ],
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 20))
            offset = int(request.query_params.get("offset", 0))

            # Pending requests where the current user is the recipient
            queryset = Friendship.objects.filter(
                to_user=request.user, status="pending"
            ).select_related("from_user")
            total = queryset.count()
            items = queryset[offset : offset + limit]
            serializer = FriendshipMinimalSerializer(
                items, many=True, context={"request": request}
            )

            base_url = request.build_absolute_uri(request.path)
            next_url = (
                f"{base_url}?limit={limit}&offset={offset + limit}"
                if offset + limit < total
                else None
            )
            prev_url = (
                f"{base_url}?limit={limit}&offset={max(0, offset - limit)}"
                if offset > 0
                else None
            )

            data = {
                "count": total,
                "next": next_url,
                "previous": prev_url,
                "results": serializer.data,
            }

            return Response(
                {
                    "status": True,
                    "message": "Pending requests retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error listing pending requests")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FriendRemoveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Friendships"],
        request=FriendRemoveSerializer,
        responses={200: FriendRemoveResponseSerializer},
        description="Remove an existing friend (unfriend).",
        examples=[
            OpenApiExample(
                "Example request",
                value={"friend_id": 123},
                request_only=True,
            ),
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "Friend removed.",
                    "data": {
                        "success": True,
                        "message": "Friend removed successfully.",
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        try:
            serializer = FriendRemoveSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            friend_id = serializer.validated_data["friend_id"]
            friend = get_object_or_404(User, pk=friend_id)

            # Find the friendship record where user is current user and friend is the target
            friendship = Friendship.objects.filter(
                from_user=request.user, to_user=friend, status="accepted"
            ).first()
            if not friendship:
                friendship = Friendship.objects.filter(
                    from_user=friend, to_user=request.user, status="accepted"
                ).first()
            if not friendship:
                return Response(
                    {
                        "status": False,
                        "message": "You are not friends with this user.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            success = FriendshipService.remove_friendship(friendship)
            if success:
                return Response(
                    {
                        "status": True,
                        "message": "Friend removed.",
                        "data": {
                            "success": True,
                            "message": "Friend removed successfully.",
                        },
                    }
                )
            else:
                return Response(
                    {
                        "status": False,
                        "message": "Failed to remove friend.",
                        "data": None,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except Exception as e:
            logger.exception("Error removing friend")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FriendTagUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Friendships"],
        request=TagUpdateSerializer,
        responses={200: TagUpdateResponseSerializer},
        description="Update the tag (e.g., favorite, family) for a friend.",
        examples=[
            OpenApiExample(
                "Example request",
                value={"tag": "bestfriend"},
                request_only=True,
            ),
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "Tag updated.",
                    "data": {"success": True, "message": "Tag updated successfully."},
                },
                response_only=True,
            ),
        ],
    )
    def patch(self, request, pk):
        try:
            friendship = get_object_or_404(Friendship, pk=pk)
            if friendship.from_user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only update tags for your own friendships.",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = TagUpdateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            new_tag = serializer.validated_data["tag"]
            updated = FriendshipService.update_tag(friendship, new_tag)
            if updated:
                return Response(
                    {
                        "status": True,
                        "message": "Tag updated.",
                        "data": {
                            "success": True,
                            "message": "Tag updated successfully.",
                        },
                    }
                )
            else:
                return Response(
                    {
                        "status": False,
                        "message": "Failed to update tag.",
                        "data": None,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except Exception as e:
            logger.exception("Error updating friend tag")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
