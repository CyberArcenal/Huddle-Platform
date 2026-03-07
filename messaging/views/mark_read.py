from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from messaging.models import Conversation, Message


class MarkMessagesReadView(APIView):
    permission_classes = [IsAuthenticated]

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