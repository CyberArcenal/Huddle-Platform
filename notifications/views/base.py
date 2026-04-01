from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
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
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_notifications(paginator, page, request):
    """
    Construct a paginated data dict that matches the expected structure.
    """
    serializer = NotificationSerializer(page, many=True, context={'request': request})
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

class PaginatedNotificationData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = NotificationSerializer(many=True)


class NotificationListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedNotificationData()


class NotificationUnreadCountResponseData(serializers.Serializer):
    unread_count = serializers.IntegerField()


class NotificationUnreadCountResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = NotificationUnreadCountResponseData()


class NotificationDetailResponseData(serializers.Serializer):
    notification = NotificationSerializer()


class NotificationDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = NotificationDetailResponseData()


class NotificationUpdateResponseData(serializers.Serializer):
    notification = NotificationSerializer()


class NotificationUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = NotificationUpdateResponseData()


class NotificationDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class NotificationMarkReadResponseData(serializers.Serializer):
    # For single notification mark
    notification = NotificationSerializer(required=False)
    # For mark all
    message = serializers.CharField(required=False)


class NotificationMarkReadResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = NotificationMarkReadResponseData(allow_null=True)


class NotificationMarkAllReadResponseData(serializers.Serializer):
    message = serializers.CharField()


class NotificationMarkAllReadResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = NotificationMarkAllReadResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class NotificationListView(APIView):
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
        responses={200: NotificationListResponseSerializer},
        description="Retrieve paginated list of notifications for the current user, newest first.",
    )
    def get(self, request):
        try:
            queryset = Notification.objects.filter(user=request.user).order_by(
                "-created_at"
            )
            paginator = NotificationPagination()
            page = paginator.paginate_queryset(queryset, request)
            paginated_data = wrap_paginated_notifications(paginator, page, request)
            return Response(
                {
                    "status": True,
                    "message": "Notifications retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error listing notifications")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notification's"],
        responses={200: NotificationUnreadCountResponseSerializer},
        examples=[
            OpenApiExample(
                "Success response",
                value={
                    "status": True,
                    "message": "Unread count retrieved.",
                    "data": {"unread_count": 5},
                },
                response_only=True,
            )
        ],
        description="Get the number of unread notifications for the current user.",
    )
    def get(self, request):
        try:
            count = Notification.objects.filter(user=request.user, is_read=False).count()
            return Response(
                {
                    "status": True,
                    "message": "Unread count retrieved.",
                    "data": {"unread_count": count},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving unread count")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NotificationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        return get_object_or_404(Notification, pk=pk, user=user)

    @extend_schema(
        tags=["Notification's"],
        responses={200: NotificationDetailResponseSerializer},
        description="Retrieve a single notification by ID.",
    )
    def get(self, request, pk):
        try:
            notification = self.get_object(pk, request.user)
            data = NotificationSerializer(notification, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Notification retrieved.",
                    "data": {"notification": data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving notification %s", pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Notification's"],
        request=NotificationSerializer,
        responses={200: NotificationUpdateResponseSerializer},
        examples=[
            OpenApiExample("Mark as read", value={"is_read": True}, request_only=True)
        ],
        description="Update a notification (e.g., mark as read).",
    )
    def patch(self, request, pk):
        try:
            notification = self.get_object(pk, request.user)
            serializer = NotificationSerializer(
                notification, data=request.data, partial=True, context={"request": request}
            )
            if serializer.is_valid():
                updated = serializer.save()
                data = NotificationSerializer(updated, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Notification updated.",
                        "data": {"notification": data},
                    }
                )
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error updating notification %s", pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Notification's"],
        responses={204: NotificationDeleteResponseSerializer},
        description="Delete a notification.",
    )
    @transaction.atomic
    def delete(self, request, pk):
        try:
            notification = self.get_object(pk, request.user)
            notification.delete()
            return Response(
                {
                    "status": True,
                    "message": "Notification deleted.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        except Exception as e:
            logger.exception("Error deleting notification %s", pk)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notification's"],
        request=NotificationMarkReadSerializer,
        responses={200: NotificationMarkReadResponseSerializer},
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
                    "status": True,
                    "message": "Notification marked as read.",
                    "data": {
                        "notification": {
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
                        }
                    },
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Response for mark all",
                value={
                    "status": True,
                    "message": "5 notifications marked as read.",
                    "data": {"message": "5 notifications marked as read."},
                },
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
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        if data.get("mark_all"):
            updated = Notification.objects.filter(
                user=request.user, is_read=False
            ).update(is_read=True)
            return Response(
                {
                    "status": True,
                    "message": f"{updated} notifications marked as read.",
                    "data": {"message": f"{updated} notifications marked as read."},
                }
            )
        else:
            notification_id = data.get("id")
            if not notification_id:
                return Response(
                    {
                        "status": False,
                        "message": "id required when mark_all is false",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                notification = get_object_or_404(
                    Notification, pk=notification_id, user=request.user
                )
                notification.is_read = True
                notification.save(update_fields=["is_read"])
                data = NotificationSerializer(notification, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Notification marked as read.",
                        "data": {"notification": data},
                    }
                )
            except Exception as e:
                logger.exception("Error marking notification %s as read", notification_id)
                return Response(
                    {
                        "status": False,
                        "message": "Something went wrong.",
                        "data": None,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notification's"],
        responses={200: NotificationMarkAllReadResponseSerializer},
        examples=[
            OpenApiExample(
                "Success response",
                value={
                    "status": True,
                    "message": "5 notifications marked as read.",
                    "data": {"message": "5 notifications marked as read."},
                },
                response_only=True,
            )
        ],
        description="Mark all unread notifications as read.",
    )
    @transaction.atomic
    def post(self, request):
        try:
            updated = Notification.objects.filter(user=request.user, is_read=False).update(
                is_read=True
            )
            return Response(
                {
                    "status": True,
                    "message": f"{updated} notifications marked as read.",
                    "data": {"message": f"{updated} notifications marked as read."},
                }
            )
        except Exception as e:
            logger.exception("Error marking all notifications as read")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )