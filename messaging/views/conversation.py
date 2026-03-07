from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import MessagingPagination
from messaging.models import Conversation
from messaging.serializers.base import ConversationSerializer, ConversationCreateSerializer


class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='page', type=int, description='Page number', required=False),
            OpenApiParameter(name='page_size', type=int, description='Results per page', required=False),
        ],
        responses={200: ConversationSerializer(many=True)},
        description="List all conversations the current user participates in, ordered by most recent activity."
    )
    def get(self, request):
        conversations = Conversation.objects.filter(participants=request.user).order_by('-updated_at')
        paginator = MessagingPagination()
        page = paginator.paginate_queryset(conversations, request)
        serializer = ConversationSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=ConversationCreateSerializer,
        responses={201: ConversationSerializer},
        examples=[
            OpenApiExample(
                'Create direct conversation',
                value={
                    'conversation_type': 'direct',
                    'participant_ids': [2, 3]
                },
                request_only=True
            ),
            OpenApiExample(
                'Create group conversation',
                value={
                    'name': 'Project Chat',
                    'conversation_type': 'group',
                    'participant_ids': [2, 3, 4]
                },
                request_only=True
            ),
            OpenApiExample(
                'Conversation response',
                value={
                    'id': 1,
                    'name': 'Project Chat',
                    'conversation_type': 'group',
                    'participants': [1, 2, 3, 4],
                    'participants_details': [
                        {'id': 1, 'username': 'alice'},
                        {'id': 2, 'username': 'bob'}
                    ],
                    'last_message': None,
                    'created_at': '2025-03-07T12:34:56Z',
                    'updated_at': '2025-03-07T12:34:56Z'
                },
                response_only=True
            )
        ],
        description="Create a new conversation. The current user is automatically added to participants."
    )
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

    @extend_schema(
        responses={200: ConversationSerializer},
        description="Retrieve details of a specific conversation."
    )
    def get(self, request, pk):
        conversation = self.get_object(pk, request.user)
        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        responses={204: None},
        description="Delete a conversation. Only participants can delete (or you may choose to just leave)."
    )
    def delete(self, request, pk):
        conversation = self.get_object(pk, request.user)
        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)