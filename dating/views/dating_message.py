# dating/views/dating_message.py
import json
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from dating.models.dating_message import DatingMessage
from dating.serializers.dating_message import (
    DatingMessageDetailSerializer,
    DatingMessageCreateSerializer,
    DatingMessageDetailSerializer,
)
from dating.services.dating_message import DatingMessageService
from users.models import User

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class DatingMessageSendResponseData(serializers.Serializer):
    message = DatingMessageDetailSerializer()


class DatingMessageSendResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = DatingMessageSendResponseData()


class PaginatedDatingMessagesData(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = DatingMessageDetailSerializer(many=True)


class DatingMessageListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedDatingMessagesData()


class DatingMessageMarkReadResponseData(serializers.Serializer):
    message = DatingMessageDetailSerializer()


class DatingMessageMarkReadResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = DatingMessageMarkReadResponseData()


# ----------------------------------------------------------------------
# Helper to build paginated response data
# ----------------------------------------------------------------------
def build_paginated_response(request, queryset, serializer_class, limit, offset):
    """Return a data dict that matches PaginatedDatingMessagesData."""
    total = queryset.count()
    messages = queryset[offset:offset + limit]
    serializer = serializer_class(messages, many=True, context={'request': request})

    base_url = request.build_absolute_uri(request.path)
    next_url = None
    prev_url = None
    if offset + limit < total:
        next_url = f"{base_url}?limit={limit}&offset={offset + limit}"
    if offset > 0:
        prev_url = f"{base_url}?limit={limit}&offset={max(0, offset - limit)}"

    return {
        "count": total,
        "next": next_url,
        "previous": prev_url,
        "results": serializer.data,
    }


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class DatingMessageSendView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Dating Messages"],
        request=DatingMessageCreateSerializer,
        responses={201: DatingMessageSendResponseSerializer},
        description="Send a new message to another user. Broadcasts via WebSocket to the conversation group.",
        examples=[
            OpenApiExample(
                "Example request",
                value={"receiver": 123, "content": "Hello!"},
                request_only=True,
            ),
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "Message sent.",
                    "data": {
                        "message": {
                            "id": 1,
                            "sender": {"id": 1, "username": "alice", "first_name": "Alice", "last_name": "Smith", "avatar": None},
                            "receiver": {"id": 123, "username": "bob", "first_name": "Bob", "last_name": "Johnson", "avatar": None},
                            "content": "Hello!",
                            "created_at": "2025-03-27T12:00:00Z",
                            "is_read": False,
                        }
                    },
                },
                response_only=True,
            ),
        ],
    )
    @transaction.atomic
    def post(self, request):
        serializer = DatingMessageCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.save()

        # Broadcast via WebSocket
        group_name = f"dating_chat_{sorted([message.sender.id, message.receiver.id])}"
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "chat_message",
                "message_id": message.id,
                "sender_id": message.sender.id,
                "sender_username": message.sender.username,
                "receiver_id": message.receiver.id,
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
                "is_read": message.is_read,
            }
        )

        output_serializer = DatingMessageDetailSerializer(message, context={'request': request})
        return Response(
            {
                "status": True,
                "message": "Message sent.",
                "data": {"message": output_serializer.data},
            },
            status=status.HTTP_201_CREATED,
        )


class DatingMessageInboxView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Dating Messages"],
        parameters=[
            OpenApiParameter(name="limit", type=int, description="Number of results per page", required=False),
            OpenApiParameter(name="offset", type=int, description="Offset for pagination", required=False),
        ],
        responses={200: DatingMessageListResponseSerializer},
        description="Get paginated list of received messages.",
        examples=[
            OpenApiExample(
                "Paginated response",
                value={
                    "status": True,
                    "message": "Inbox retrieved.",
                    "data": {
                        "count": 2,
                        "next": "http://example.com/messages/inbox/?limit=10&offset=10",
                        "previous": None,
                        "results": [
                            {
                                "id": 1,
                                "sender": {"id": 1, "username": "alice", "first_name": "Alice", "last_name": "Smith", "avatar": None},
                                "receiver": {"id": 2, "username": "bob", "first_name": "Bob", "last_name": "Johnson", "avatar": None},
                                "content": "Hello!",
                                "created_at": "2025-03-27T12:00:00Z",
                                "is_read": False,
                            }
                        ]
                    }
                }
            )
        ]
    )
    def get(self, request):
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        queryset = DatingMessageService.list_inbox(request.user)
        data = build_paginated_response(request, queryset, DatingMessageDetailSerializer, limit, offset)
        return Response(
            {
                "status": True,
                "message": "Inbox retrieved.",
                "data": data,
            }
        )


class DatingMessageSentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Dating Messages"],
        parameters=[
            OpenApiParameter(name="limit", type=int, description="Number of results per page", required=False),
            OpenApiParameter(name="offset", type=int, description="Offset for pagination", required=False),
        ],
        responses={200: DatingMessageListResponseSerializer},
        description="Get paginated list of sent messages.",
    )
    def get(self, request):
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        queryset = DatingMessageService.list_sent(request.user)
        data = build_paginated_response(request, queryset, DatingMessageDetailSerializer, limit, offset)
        return Response(
            {
                "status": True,
                "message": "Sent messages retrieved.",
                "data": data,
            }
        )


class DatingMessageConversationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Dating Messages"],
        parameters=[
            OpenApiParameter(name="limit", type=int, description="Number of results per page", required=False),
            OpenApiParameter(name="offset", type=int, description="Offset for pagination", required=False),
        ],
        responses={200: DatingMessageListResponseSerializer},
        description="Get paginated conversation with another user.",
    )
    def get(self, request, user_id):
        other_user = get_object_or_404(User, pk=user_id)
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        queryset = DatingMessageService.get_conversation(request.user, other_user)
        data = build_paginated_response(request, queryset, DatingMessageDetailSerializer, limit, offset)
        return Response(
            {
                "status": True,
                "message": "Conversation retrieved.",
                "data": data,
            }
        )


class DatingMessageMarkReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Dating Messages"],
        responses={200: DatingMessageMarkReadResponseSerializer},
        description="Mark a specific message as read.",
        examples=[
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "Message marked as read.",
                    "data": {
                        "message": {
                            "id": 1,
                            "sender": {"id": 1, "username": "alice", "first_name": "Alice", "last_name": "Smith", "avatar": None},
                            "receiver": {"id": 2, "username": "bob", "first_name": "Bob", "last_name": "Johnson", "avatar": None},
                            "content": "Hello!",
                            "created_at": "2025-03-27T12:00:00Z",
                            "is_read": True,
                        }
                    },
                },
                response_only=True,
            ),
        ],
    )
    def patch(self, request, pk):
        message = get_object_or_404(DatingMessage, pk=pk)
        if message.receiver != request.user:
            return Response(
                {
                    "status": False,
                    "message": "You are not the receiver of this message.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        message = DatingMessageService.mark_as_read(message)
        serializer = DatingMessageDetailSerializer(message, context={'request': request})
        return Response(
            {
                "status": True,
                "message": "Message marked as read.",
                "data": {"message": serializer.data},
            }
        )