from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import MessagingPagination
from messaging.models import Conversation, Message
from messaging.serializers.base import MessageSerializer, MessageCreateSerializer
import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_messages(paginator, page, request):
    """
    Construct a paginated data dict that matches the expected structure.
    """
    serializer = MessageSerializer(page, many=True, context={'request': request})
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

class PaginatedMessageData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = MessageSerializer(many=True)


class MessageListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedMessageData()


class MessageCreateResponseData(serializers.Serializer):
    message = MessageSerializer()


class MessageCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MessageCreateResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class MessageListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["Chat"],
        parameters=[
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: MessageListResponseSerializer},
        description="Retrieve paginated list of messages in a conversation (oldest first)."
    )
    def get(self, request, conversation_pk):
        try:
            conversation = get_object_or_404(Conversation, pk=conversation_pk)
            if request.user not in conversation.participants.all():
                return Response(
                    {
                        "status": False,
                        "message": "Not a participant",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            messages = conversation.messages.filter(is_deleted=False).order_by("created_at")
            paginator = MessagingPagination()
            page = paginator.paginate_queryset(messages, request)
            paginated_data = wrap_paginated_messages(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Messages retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error listing messages in conversation %s", conversation_pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Chat"],
        request=MessageCreateSerializer,
        responses={201: MessageCreateResponseSerializer},
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
                    "status": True,
                    "message": "Message sent.",
                    "data": {
                        "message": {
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
                        }
                    },
                },
                response_only=True,
            ),
        ],
    )
    @transaction.atomic
    def post(self, request, conversation_pk):
        try:
            conversation = get_object_or_404(Conversation, pk=conversation_pk)
            if request.user not in conversation.participants.all():
                return Response(
                    {
                        "status": False,
                        "message": "Not a participant",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            data = request.data.copy()
            data["conversation"] = conversation.id
            serializer = MessageCreateSerializer(data=data, context={"request": request})
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            message = serializer.save()

            # Update conversation's updated_at timestamp
            conversation.save(update_fields=["updated_at"])

            # Broadcast via WebSocket
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

            response_data = MessageSerializer(message, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Message sent.",
                    "data": {"message": response_data},
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception("Error sending message in conversation %s", conversation_pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )