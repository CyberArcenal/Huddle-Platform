from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q

from global_utils.pagination import NotificationPagination
from notifications.models import Notification
from notifications.serializers.base import NotificationSerializer, NotificationMarkReadSerializer


class NotificationListView(APIView):
    """List all notifications for the authenticated user (paginated)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Notification.objects.filter(user=request.user).order_by('-created_at')
        paginator = NotificationPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = NotificationSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class NotificationUnreadCountView(APIView):
    """Get count of unread notifications."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'unread_count': count})


class NotificationDetailView(APIView):
    """Retrieve, update (mark read), or delete a specific notification."""
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        return get_object_or_404(Notification, pk=pk, user=user)

    def get(self, request, pk):
        notification = self.get_object(pk, request.user)
        serializer = NotificationSerializer(notification, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        notification = self.get_object(pk, request.user)
        serializer = NotificationSerializer(notification, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        notification = self.get_object(pk, request.user)
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationMarkReadView(APIView):
    """Mark one or all notifications as read."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = NotificationMarkReadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        if data.get('mark_all'):
            # Mark all unread notifications as read
            updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
            return Response({'message': f'{updated} notifications marked as read.'})
        else:
            # Mark a single notification as read
            notification_id = data.get('id')
            if not notification_id:
                return Response({'error': 'id required when mark_all is false'}, status=status.HTTP_400_BAD_REQUEST)
            notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
            notification.is_read = True
            notification.save(update_fields=['is_read'])
            serializer = NotificationSerializer(notification, context={'request': request})
            return Response(serializer.data)


class NotificationMarkAllReadView(APIView):
    """Convenience endpoint to mark all as read."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': f'{updated} notifications marked as read.'})