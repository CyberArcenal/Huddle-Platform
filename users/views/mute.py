# dating/views/mute.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from users.models import User
from users.serializers.mute import MutedUserCreateSerializer, MutedUserDetailSerializer, MutedUserMinimalSerializer, UnMuteUserCreateSerializer
from users.services.mute import MutedUserService

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to build paginated data
# ----------------------------------------------------------------------
def build_paginated_muted_data(request, queryset, serializer_class, limit, offset):
    """
    Build paginated data dict for muted users list.
    """
    total = queryset.count()
    items = queryset[offset:offset + limit]
    serializer = serializer_class(items, many=True, context={'request': request})

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

class MuteResponseData(serializers.Serializer):
    muted = MutedUserDetailSerializer()


class MuteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MuteResponseData()


class UnmuteResponseData(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()


class UnmuteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UnmuteResponseData()


class PaginatedMutedUsersData(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = MutedUserMinimalSerializer(many=True)


class PaginatedMutedUsersResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedMutedUsersData()


class CheckMutedResponseData(serializers.Serializer):
    muted = serializers.BooleanField()


class CheckMutedResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = CheckMutedResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class MuteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Muting"],
        request=MutedUserCreateSerializer,
        responses={201: MuteResponseSerializer},
        description="Mute another user. Cannot mute yourself.",
        examples=[
            OpenApiExample(
                "Example request",
                value={"muted": 123},
                request_only=True,
            ),
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "User muted.",
                    "data": {
                        "muted": {
                            "id": 1,
                            "user": {"id": 1, "username": "alice", "first_name": "Alice", "last_name": "Smith", "avatar": None},
                            "muted": {"id": 123, "username": "bob", "first_name": "Bob", "last_name": "Johnson", "avatar": None},
                            "created_at": "2025-03-27T12:00:00Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        try:
            serializer = MutedUserCreateSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            muted_record = serializer.save()
            output_serializer = MutedUserDetailSerializer(muted_record, context={'request': request})
            return Response(
                {
                    "status": True,
                    "message": "User muted.",
                    "data": {"muted": output_serializer.data},
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception("Error muting user")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UnmuteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Muting"],
        request=UnMuteUserCreateSerializer,
        responses={200: UnmuteResponseSerializer},
        description="Unmute a previously muted user.",
        examples=[
            OpenApiExample(
                "Example request",
                value={"muted": 123},
                request_only=True,
            ),
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "User unmuted.",
                    "data": {"success": True, "message": "User unmuted successfully."},
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        try:
            serializer = UnMuteUserCreateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            muted_user = serializer.validated_data['muted']
            MutedUserService.unmute_user(request.user, muted_user)
            return Response(
                {
                    "status": True,
                    "message": "User unmuted.",
                    "data": {"success": True, "message": "User unmuted successfully."},
                }
            )
        except Exception as e:
            logger.exception("Error unmuting user")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MutedUsersListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Muting"],
        parameters=[
            OpenApiParameter(name="limit", type=int, description="Number of results per page", required=False),
            OpenApiParameter(name="offset", type=int, description="Offset for pagination", required=False),
        ],
        responses={200: PaginatedMutedUsersResponseSerializer},
        description="Get paginated list of users muted by the current user.",
        examples=[
            OpenApiExample(
                "Paginated response",
                value={
                    "status": True,
                    "message": "Muted users list retrieved.",
                    "data": {
                        "count": 2,
                        "next": "http://example.com/mutes/?limit=10&offset=10",
                        "previous": None,
                        "results": [
                            {
                                "id": 1,
                                "muted": {"id": 123, "username": "bob", "first_name": "Bob", "last_name": "Johnson", "avatar": None},
                                "created_at": "2025-03-27T12:00:00Z",
                            }
                        ]
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 20))
            offset = int(request.query_params.get('offset', 0))

            queryset = MutedUserService.list_muted_users(request.user)
            data = build_paginated_muted_data(
                request, queryset, MutedUserMinimalSerializer, limit, offset
            )
            return Response(
                {
                    "status": True,
                    "message": "Muted users list retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error listing muted users")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CheckMutedView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Muting"],
        responses={200: CheckMutedResponseSerializer},
        description="Check if the current user has muted another user.",
        examples=[
            OpenApiExample(
                "Example response (muted)",
                value={"status": True, "message": "Check completed.", "data": {"muted": True}},
                response_only=True,
            ),
            OpenApiExample(
                "Example response (not muted)",
                value={"status": True, "message": "Check completed.", "data": {"muted": False}},
                response_only=True,
            ),
        ],
    )
    def get(self, request, user_id):
        try:
            other_user = get_object_or_404(User, pk=user_id)
            is_muted = MutedUserService.is_muted(request.user, other_user)
            return Response(
                {
                    "status": True,
                    "message": "Check completed.",
                    "data": {"muted": is_muted},
                }
            )
        except Exception as e:
            logger.exception("Error checking muted status")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )