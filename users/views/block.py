# dating/views/blocked.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from users.models import User
from users.serializers.block import BlockedUserCreateSerializer, BlockedUserDetailSerializer, BlockedUserMinimalSerializer
from users.services.block import BlockedUserService

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_blocked_users(request, queryset, limit, offset):
    """
    Build paginated data dict for blocked users.
    """
    total = queryset.count()
    blocked_users = queryset[offset:offset + limit]
    serializer = BlockedUserMinimalSerializer(blocked_users, many=True, context={'request': request})

    base_url = request.build_absolute_uri(request.path)
    next_url = f"{base_url}?limit={limit}&offset={offset + limit}" if offset + limit < total else None
    prev_url = f"{base_url}?limit={limit}&offset={max(0, offset - limit)}" if offset > 0 else None

    return {
        "count": total,
        "next": next_url,
        "previous": prev_url,
        "results": serializer.data,
    }


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class BlockResponseData(serializers.Serializer):
    block = BlockedUserDetailSerializer()


class BlockResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = BlockResponseData()


class UnblockResponseData(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()


class UnblockResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UnblockResponseData()


class BlockedUsersListResponseData(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = BlockedUserMinimalSerializer(many=True)


class BlockedUsersListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = BlockedUsersListResponseData()


class CheckBlockedResponseData(serializers.Serializer):
    blocked = serializers.BooleanField()


class CheckBlockedResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = CheckBlockedResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class BlockView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Blocking"],
        request=BlockedUserCreateSerializer,
        responses={201: BlockResponseSerializer},
        description="Block another user. Cannot block yourself.",
        examples=[
            OpenApiExample(
                "Example request",
                value={"blocked": 123},
                request_only=True,
            ),
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "User blocked.",
                    "data": {
                        "block": {
                            "id": 1,
                            "user": {"id": 1, "username": "alice", "first_name": "Alice", "last_name": "Smith", "avatar": None},
                            "blocked": {"id": 123, "username": "bob", "first_name": "Bob", "last_name": "Johnson", "avatar": None},
                            "created_at": "2025-03-27T12:00:00Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = BlockedUserCreateSerializer(data=request.data, context={'request': request})
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        blocked_record = serializer.save()
        output_serializer = BlockedUserDetailSerializer(blocked_record, context={'request': request})
        return Response(
            {
                "status": True,
                "message": "User blocked.",
                "data": {"block": output_serializer.data},
            },
            status=status.HTTP_201_CREATED,
        )


class UnblockView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    class UnblockUserSerializer(serializers.Serializer):
        blocked = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True)

    @extend_schema(
        tags=["Blocking"],
        request=UnblockUserSerializer,
        responses={200: UnblockResponseSerializer},
        description="Unblock a previously blocked user.",
        examples=[
            OpenApiExample(
                "Example request",
                value={"blocked": 123},
                request_only=True,
            ),
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "User unblocked.",
                    "data": {"success": True, "message": "User unblocked successfully."},
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = self.UnblockUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        blocked_user = serializer.validated_data['blocked']
        try:
            BlockedUserService.unblock_user(request.user, blocked_user)
            return Response(
                {
                    "status": True,
                    "message": "User unblocked.",
                    "data": {"success": True, "message": "User unblocked successfully."},
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("UnblockView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class BlockedUsersListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Blocking"],
        parameters=[
            OpenApiParameter(name="limit", type=int, description="Number of results per page", required=False),
            OpenApiParameter(name="offset", type=int, description="Offset for pagination", required=False),
        ],
        responses={200: BlockedUsersListResponseSerializer},
        description="Get paginated list of users blocked by the current user.",
        examples=[
            OpenApiExample(
                "Paginated response",
                value={
                    "status": True,
                    "message": "Blocked users retrieved.",
                    "data": {
                        "count": 2,
                        "next": "http://example.com/blocks/?limit=10&offset=10",
                        "previous": None,
                        "results": [
                            {
                                "id": 1,
                                "blocked": {"id": 123, "username": "bob", "first_name": "Bob", "last_name": "Johnson", "avatar": None},
                                "created_at": "2025-03-27T12:00:00Z",
                            }
                        ]
                    }
                }
            )
        ],
    )
    def get(self, request):
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))

        queryset = BlockedUserService.list_blocked_users(request.user)
        paginated_data = wrap_paginated_blocked_users(request, queryset, limit, offset)

        return Response(
            {
                "status": True,
                "message": "Blocked users retrieved.",
                "data": paginated_data,
            }
        )


class CheckBlockedView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Blocking"],
        responses={200: CheckBlockedResponseSerializer},
        description="Check if the current user has blocked another user.",
        examples=[
            OpenApiExample(
                "Example response (blocked)",
                value={"status": True, "message": "Block status checked.", "data": {"blocked": True}},
                response_only=True,
            ),
            OpenApiExample(
                "Example response (not blocked)",
                value={"status": True, "message": "Block status checked.", "data": {"blocked": False}},
                response_only=True,
            ),
        ],
    )
    def get(self, request, user_id):
        other_user = get_object_or_404(User, pk=user_id)
        is_blocked = BlockedUserService.is_blocked(request.user, other_user)
        return Response(
            {
                "status": True,
                "message": "Block status checked.",
                "data": {"blocked": is_blocked},
            }
        )