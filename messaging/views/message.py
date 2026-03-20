from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import MessagingPagination
from messaging.models import Conversation, Message
from messaging.serializers.base import MessageSerializer, MessageCreateSerializer
from rest_framework import serializers
from messaging.serializers.base import MessageSerializer

# ----- Paginated response serializer for drf-spectacular -----
class PaginatedMessageSerializer(serializers.Serializer):
    """Matches the custom pagination response from MessagingPagination"""
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = MessageSerializer(many=True)
# --------------------------------------------------------------

class MessageListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["Chat"],
        parameters=[
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: PaginatedMessageSerializer},
        description="Retrieve paginated list of messages in a conversation (oldest first)."
    )
    def get(self, request, conversation_pk):
        conversation = get_object_or_404(Conversation, pk=conversation_pk)
        if request.user not in conversation.participants.all():
            return Response(
                {"detail": "Not a participant"}, status=status.HTTP_403_FORBIDDEN
            )

        messages = conversation.messages.filter(is_deleted=False).order_by("created_at")
        paginator = MessagingPagination()
        page = paginator.paginate_queryset(messages, request)
        serializer = MessageSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Chat"],
        request=MessageCreateSerializer,
        responses={201: MessageSerializer},
        description="Create a new message (text or media) in a conversation.",
        examples=[
            OpenApiExample(
                "Create text message",
                value={
                    "content": "Hello, how are you?",
                    "media": None,
                    "media_type": None,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create image message",
                value={
                    "content": "Check out this photo!",
                    "media": "binary file data",
                    "media_type": "image",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Successful response",
                value={
                    "id": 123,
                    "conversation": 1,
                    "sender": 1,
                    "sender_details": {
                        "id": 1,
                        "username": "john_doe",
                        "email": "john@example.com",
                    },
                    "content": "Hello, how are you?",
                    "media": None,
                    "media_url": None,
                    "media_type": None,
                    "is_read": False,
                    "is_deleted": False,
                    "created_at": "2025-03-07T12:34:56Z",
                },
                response_only=True,
            ),
        ],
    )
    @transaction.atomic
    def post(self, request, conversation_pk):
        conversation = get_object_or_404(Conversation, pk=conversation_pk)
        if request.user not in conversation.participants.all():
            return Response(
                {"detail": "Not a participant"}, status=status.HTTP_403_FORBIDDEN
            )

        data = request.data.copy()
        data["conversation"] = conversation.id
        serializer = MessageCreateSerializer(data=data, context={"request": request})
        if serializer.is_valid():
            message = serializer.save()

            # Update conversation's updated_at timestamp
            conversation.save(update_fields=["updated_at"])

            # Broadcast via WebSocket to all participants
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    "type": "chat_message",
                    "message_id": message.id,
                    "sender_id": message.sender.id,
                    "sender_username": message.sender.username,
                    "content": message.content,
                    "media_url": message.media.url if message.media else None,
                    "media_type": message.media_type,
                    "timestamp": str(message.created_at),
                },
            )

            return Response(
                MessageSerializer(message, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)