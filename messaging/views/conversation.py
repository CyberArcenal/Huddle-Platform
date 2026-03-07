from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from global_utils.pagination import MessagingPagination
from messaging.models import Conversation
from messaging.serializers.base import ConversationSerializer, ConversationCreateSerializer


class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        conversations = Conversation.objects.filter(participants=request.user).order_by('-updated_at')
        paginator = MessagingPagination()
        page = paginator.paginate_queryset(conversations, request)
        serializer = ConversationSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = ConversationCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            conversation = serializer.save()
            return Response(
                ConversationSerializer(conversation, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        conv = get_object_or_404(Conversation, pk=pk)
        if user not in conv.participants.all():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not a participant of this conversation")
        return conv

    def get(self, request, pk):
        conversation = self.get_object(pk, request.user)
        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data)

    def delete(self, request, pk):
        conversation = self.get_object(pk, request.user)
        # Optionally, delete conversation (or just leave it – up to you)
        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)