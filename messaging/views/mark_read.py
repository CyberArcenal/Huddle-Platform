from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema, OpenApiExample

from messaging.models import Conversation, Message


class MarkMessagesReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: {'type': 'object', 'properties': {'marked_read': {'type': 'integer'}}}},
        examples=[
            OpenApiExample(
                'Success response',
                value={'marked_read': 3},
                response_only=True
            )
        ],
        description="Mark all unread messages in a conversation as read (except those sent by the current user)."
    )
    def post(self, request, conversation_pk):
        conversation = get_object_or_404(Conversation, pk=conversation_pk)
        if request.user not in conversation.participants.all():
            return Response({'detail': 'Not a participant'}, status=status.HTTP_403_FORBIDDEN)

        # Mark all unread messages in this conversation as read
        updated = Message.objects.filter(
            conversation=conversation,
            is_read=False
        ).exclude(sender=request.user).update(is_read=True)

        return Response({'marked_read': updated})