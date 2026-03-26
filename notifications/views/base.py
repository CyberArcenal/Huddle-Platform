from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import NotificationPagination
from notifications.models import Notification
from notifications.serializers.base import (
    NotificationSerializer,
    NotificationMarkReadSerializer,
)
from rest_framework import serializers
from notifications.serializers.base import NotificationSerializer
from django.db import transaction

# ----- Paginated response serializer for drf-spectacular -----
class PaginatedNotificationSerializer(serializers.Serializer):
    """Matches the custom pagination response from NotificationPagination"""

    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = NotificationSerializer(many=True)


# --------------------------------------------------------------


class NotificationListView(APIView):
    """List all notifications for the authenticated user (paginated)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notification's"],
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
        responses={200: PaginatedNotificationSerializer},
        description="Retrieve paginated list of notifications for the current user, newest first.",
    )
    def get(self, request):
        queryset = Notification.objects.filter(user=request.user).order_by(
            "-created_at"
        )
        paginator = NotificationPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = NotificationSerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)


class NotificationUnreadCountView(APIView):
    """Get count of unread notifications."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notification's"],
        responses={
            200: {"type": "object", "properties": {"unread_count": {"type": "integer"}}}
        },
        examples=[
            OpenApiExample(
                "Success response", value={"unread_count": 5}, response_only=True
            )
        ],
        description="Get the number of unread notifications for the current user.",
    )
    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count})


class NotificationDetailView(APIView):
    """Retrieve, update (mark read), or delete a specific notification."""

    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        return get_object_or_404(Notification, pk=pk, user=user)

    @extend_schema(
        tags=["Notification's"],
        responses={200: NotificationSerializer},
        description="Retrieve a single notification by ID.",
    )
    def get(self, request, pk):
        notification = self.get_object(pk, request.user)
        serializer = NotificationSerializer(notification, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["Notification's"],
        request=NotificationSerializer,
        responses={200: NotificationSerializer},
        examples=[
            OpenApiExample("Mark as read", value={"is_read": True}, request_only=True)
        ],
        description="Update a notification (e.g., mark as read).",
    )
    def patch(self, request, pk):
        notification = self.get_object(pk, request.user)
        serializer = NotificationSerializer(
            notification, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["Notification's"],responses={204: None}, description="Delete a notification.")
    @transaction.atomic
    def delete(self, request, pk):
        notification = self.get_object(pk, request.user)
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationMarkReadView(APIView):
    """Mark one or all notifications as read."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notification's"],
        request=NotificationMarkReadSerializer,
        responses={200: NotificationSerializer},
        examples=[
            OpenApiExample(
                "Mark single notification", value={"id": 42}, request_only=True
            ),
            OpenApiExample(
                "Mark all notifications", value={"mark_all": True}, request_only=True
            ),
            OpenApiExample(
                "Response for single mark",
                value={
                    "id": 42,
                    "user": 1,
                    "actor": 2,
                    "notification_type": "like",
                    "message": "John liked your post",
                    "is_read": True,
                    "related_id": 123,
                    "related_model": "Post",
                    "created_at": "2025-03-07T12:34:56Z",
                    "time_ago": "2 hours ago",
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Response for mark all",
                value={"message": "5 notifications marked as read."},
                response_only=True,
                status_codes=["200"],
            ),
        ],
        description='Mark a specific notification as read by providing its `id`, or mark all unread notifications as read by sending `{"mark_all": true}`.',
    )
    @transaction.atomic
    def post(self, request):
        serializer = NotificationMarkReadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        if data.get("mark_all"):
            updated = Notification.objects.filter(
                user=request.user, is_read=False
            ).update(is_read=True)
            return Response({"message": f"{updated} notifications marked as read."})
        else:
            notification_id = data.get("id")
            if not notification_id:
                return Response(
                    {"error": "id required when mark_all is false"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            notification = get_object_or_404(
                Notification, pk=notification_id, user=request.user
            )
            notification.is_read = True
            notification.save(update_fields=["is_read"])
            serializer = NotificationSerializer(
                notification, context={"request": request}
            )
            return Response(serializer.data)


class NotificationMarkAllReadView(APIView):
    """Convenience endpoint to mark all as read."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notification's"],
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
        examples=[
            OpenApiExample(
                "Success response",
                value={"message": "5 notifications marked as read."},
                response_only=True,
            )
        ],
        description="Mark all unread notifications as read.",
    )
    @transaction.atomic
    def post(self, request):
        updated = Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True
        )
        return Response({"message": f"{updated} notifications marked as read."})
