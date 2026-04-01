from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiExample

from messaging.models import Conversation, Message
import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class MarkMessagesReadResponseData(serializers.Serializer):
    marked_read = serializers.IntegerField()


class MarkMessagesReadResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MarkMessagesReadResponseData()


# ----------------------------------------------------------------------
# View
# ----------------------------------------------------------------------

class MarkMessagesReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Conversation"],
        responses={200: MarkMessagesReadResponseSerializer},
        examples=[
            OpenApiExample(
                "Success response",
                value={
                    "status": True,
                    "message": "Messages marked as read.",
                    "data": {"marked_read": 3},
                },
                response_only=True,
            )
        ],
        description="Mark all unread messages in a conversation as read (except those sent by the current user).",
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

            # Mark all unread messages in this conversation as read
            updated = (
                Message.objects.filter(conversation=conversation, is_read=False)
                .exclude(sender=request.user)
                .update(is_read=True)
            )

            return Response(
                {
                    "status": True,
                    "message": "Messages marked as read.",
                    "data": {"marked_read": updated},
                }
            )
        except Exception as e:
            logger.exception("Error marking messages read in conversation %s", conversation_pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )