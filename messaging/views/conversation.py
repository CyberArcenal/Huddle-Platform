from rest_framework.views import APIView, PermissionDenied
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import MessagingPagination
from messaging.models import Conversation
from messaging.serializers.base import (
    ConversationSerializer,
    ConversationCreateSerializer,
)
from rest_framework import serializers
import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_conversations(paginator, page, request):
    """
    Construct a paginated data dict that matches the expected structure.
    """
    serializer = ConversationSerializer(page, many=True, context={'request': request})
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

class PaginatedConversationData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ConversationSerializer(many=True)


class ConversationListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedConversationData()


class ConversationCreateResponseData(serializers.Serializer):
    conversation = ConversationSerializer()


class ConversationCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ConversationCreateResponseData()


class ConversationDetailResponseData(serializers.Serializer):
    conversation = ConversationSerializer()


class ConversationDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ConversationDetailResponseData()


class ConversationDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Conversation"],
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
        responses={200: ConversationListResponseSerializer},
        description="List all conversations the current user participates in, ordered by most recent activity.",
    )
    def get(self, request):
        try:
            conversations = Conversation.objects.filter(participants=request.user).order_by(
                "-updated_at"
            )
            paginator = MessagingPagination()
            page = paginator.paginate_queryset(conversations, request)
            paginated_data = wrap_paginated_conversations(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Conversations retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error listing conversations")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Conversation"],
        request=ConversationCreateSerializer,
        responses={201: ConversationCreateResponseSerializer},
        examples=[
            OpenApiExample(
                "Create direct conversation",
                value={"conversation_type": "direct", "participant_ids": [2, 3]},
                request_only=True,
            ),
            OpenApiExample(
                "Create group conversation",
                value={
                    "name": "Project Chat",
                    "conversation_type": "group",
                    "participant_ids": [2, 3, 4],
                },
                request_only=True,
            ),
            OpenApiExample(
                "Conversation response",
                value={
                    "status": True,
                    "message": "Conversation created.",
                    "data": {
                        "conversation": {
                            "id": 1,
                            "name": "Project Chat",
                            "conversation_type": "group",
                            "participants": [1, 2, 3, 4],
                            "participants_details": [
                                {"id": 1, "username": "alice"},
                                {"id": 2, "username": "bob"},
                            ],
                            "last_message": None,
                            "created_at": "2025-03-07T12:34:56Z",
                            "updated_at": "2025-03-07T12:34:56Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
        description="Create a new conversation. The current user is automatically added to participants.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = ConversationCreateSerializer(
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
        conversation = serializer.save()
        data = ConversationSerializer(conversation, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Conversation created.",
                "data": {"conversation": data},
            },
            status=status.HTTP_201_CREATED,
        )


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        conv = get_object_or_404(Conversation, pk=pk)
        if user not in conv.participants.all():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not a participant of this conversation")
        return conv

    @extend_schema(
        tags=["Conversation"],
        responses={200: ConversationDetailResponseSerializer},
        description="Retrieve details of a specific conversation.",
    )
    def get(self, request, pk):
        try:
            conversation = self.get_object(pk, request.user)
            data = ConversationSerializer(conversation, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Conversation retrieved.",
                    "data": {"conversation": data},
                }
            )
        except PermissionDenied as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception as e:
            logger.exception("Error retrieving conversation %s", pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Conversation"],
        responses={204: ConversationDeleteResponseSerializer},
        description="Delete a conversation. Only participants can delete (or you may choose to just leave).",
    )
    @transaction.atomic
    def delete(self, request, pk):
        try:
            conversation = self.get_object(pk, request.user)
            conversation.delete()
            return Response(
                {
                    "status": True,
                    "message": "Conversation deleted.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        except PermissionDenied as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception as e:
            logger.exception("Error deleting conversation %s", pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )