import logging
from django.core.cache import cache
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from global_utils.logger import log_audit_event
from global_utils.response import CustomPagination, _error, _success
from global_utils.security import get_client_ip


from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db import transaction
from django.utils import timezone

from notifications.models.notify_log import NotifyLog
from notifications.serializers.notify_log import (
    NotifyLogCreateSerializer,
    NotifyLogDisplaySerializer,
)
from notifications.services.email import EmailService
from notifications.services.push import PushService
from notifications.services.sms import SMSService

# Constants for caching
CACHE_TTL = 60 * 60 * 24  # 5 minutes
CACHE_PREFIX = "api:notifylog:"

logger = logging.getLogger(__name__)


class NotifyLogRetry(APIView):
    """
    Retry a failed notification.
    Only staff can access this endpoint.
    """

    @extend_schema(
        tags=["notify"],
        responses={200: None, 404: None, 403: None},
        description="Retry a failed notification by its ID.",
    )
    def post(self, request, id):
        user = request.user
        if not user.is_staff:
            return _error(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "retry"

        try:
            log_entry = NotifyLog.objects.get(pk=id)
        except NotifyLog.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id=str(id),
                changes={"error": "Log not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Log not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # Only allow retry if the current status is failed
        if log_entry.status != "failed":
            return _error(
                {"detail": "Only failed notifications can be retried."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_time = timezone.now()
        success = False
        error_message = None

        try:
            # Use the appropriate service based on channel
            if log_entry.channel == "email":
                success = EmailService.send_simple_email(
                    subject=log_entry.subject,
                    message=log_entry.payload or "",
                    recipient_list=[log_entry.recipient_email],
                    from_email=(
                        log_entry.metadata.get("from_email")
                        if log_entry.metadata
                        else None
                    ),
                )
            elif log_entry.channel == "sms":
                success = SMSService.send_sms(
                    to_number=log_entry.recipient_email,
                    message=log_entry.payload or "",
                )
            elif log_entry.channel == "push":
                success = PushService.send_push(
                    recipient_id=log_entry.recipient_email,
                    title=log_entry.subject or "Notification",
                    message=log_entry.payload or "",
                    data=log_entry.metadata or {},
                )
            else:
                logger.warning(f"Unknown channel '{log_entry.channel}' for retry {id}")
                success = False
                error_message = f"Unknown channel: {log_entry.channel}"
        except Exception as e:
            logger.exception(f"Error during retry for log {id}")
            success = False
            error_message = str(e)

        end_time = timezone.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Update the log entry
        with transaction.atomic():
            log_entry.duration_ms = duration_ms
            log_entry.retry_count += 1

            if success:
                log_entry.status = "sent"
                log_entry.sent_at = end_time
                log_entry.error_message = None
                log_entry.last_error_at = None
            else:
                log_entry.status = "failed"
                log_entry.error_message = error_message or "Unknown error"
                log_entry.last_error_at = end_time

            log_entry.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "error_message",
                    "last_error_at",
                    "duration_ms",
                    "retry_count",
                    "updated_at",
                ]
            )

        # Invalidate cache for this log and list
        try:
            cache.delete_pattern(f"{CACHE_PREFIX}*")
        except AttributeError:
            cache.clear()

        log_audit_event(
            request=request,
            user=user,
            action_type=action_type,
            model_name="NotifyLog",
            object_id=str(id),
            changes={
                "retry_count": log_entry.retry_count,
                "status": log_entry.status,
                "success": success,
            },
            ip_address=client_ip,
            user_agent=user_agent,
        )

        if success:
            return _success({"detail": "Retry successful."}, status=status.HTTP_200_OK)
        else:
            return _error(
                {"detail": error_message or "Retry failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NotifyLogResend(APIView):
    """
    Resend a notification regardless of its current status.
    Only staff can access this endpoint.
    """

    @extend_schema(
        tags=["notify"],
        responses={200: None, 404: None, 403: None},
        description="Resend a notification by its ID.",
    )
    def post(self, request, id):
        user = request.user
        if not user.is_staff:
            return _error(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "resend"

        try:
            log_entry = NotifyLog.objects.get(pk=id)
        except NotifyLog.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id=str(id),
                changes={"error": "Log not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Log not found."}, status=status.HTTP_404_NOT_FOUND
            )

        start_time = timezone.now()
        success = False
        error_message = None

        try:
            if log_entry.channel == "email":
                success = EmailService.send_simple_email(
                    subject=log_entry.subject,
                    message=log_entry.payload or "",
                    recipient_list=[log_entry.recipient_email],
                    from_email=(
                        log_entry.metadata.get("from_email")
                        if log_entry.metadata
                        else None
                    ),
                )
            elif log_entry.channel == "sms":
                success = SMSService.send_sms(
                    to_number=log_entry.recipient_email,
                    message=log_entry.payload or "",
                )
            elif log_entry.channel == "push":
                success = PushService.send_push(
                    recipient_id=log_entry.recipient_email,
                    title=log_entry.subject or "Notification",
                    message=log_entry.payload or "",
                    data=log_entry.metadata or {},
                )
            else:
                logger.warning(f"Unknown channel '{log_entry.channel}' for resend {id}")
                success = False
                error_message = f"Unknown channel: {log_entry.channel}"
        except Exception as e:
            logger.exception(f"Error during resend for log {id}")
            success = False
            error_message = str(e)

        end_time = timezone.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        with transaction.atomic():
            log_entry.duration_ms = duration_ms
            log_entry.resend_count += 1

            if success:
                log_entry.status = "sent"
                log_entry.sent_at = end_time
                log_entry.error_message = None
                log_entry.last_error_at = None
            else:
                log_entry.status = "failed"
                log_entry.error_message = error_message or "Unknown error"
                log_entry.last_error_at = end_time

            log_entry.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "error_message",
                    "last_error_at",
                    "duration_ms",
                    "resend_count",
                    "updated_at",
                ]
            )

        # Invalidate cache
        try:
            cache.delete_pattern(f"{CACHE_PREFIX}*")
        except AttributeError:
            cache.clear()

        log_audit_event(
            request=request,
            user=user,
            action_type=action_type,
            model_name="NotifyLog",
            object_id=str(id),
            changes={
                "resend_count": log_entry.resend_count,
                "status": log_entry.status,
                "success": success,
            },
            ip_address=client_ip,
            user_agent=user_agent,
        )

        if success:
            return _success({"detail": "Resend successful."}, status=status.HTTP_200_OK)
        else:
            return _error(
                {"detail": error_message or "Resend failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NotifyLogCRUD(APIView):
    pagination_class = CustomPagination

    def get_queryset(self):
        # Only staff can access logs
        if self.request.user.is_staff:
            return NotifyLog.objects.all()
        return NotifyLog.objects.none()

    def _get_list_cache_key(self, request):
        """Generate cache key for log list based on full path and staff status."""
        path = request.get_full_path()
        return f"{CACHE_PREFIX}list:staff={request.user.is_staff}:{path}"

    def _get_detail_cache_key(self, identifier, is_staff):
        """Generate cache key for a single log entry (by id)."""
        return f"{CACHE_PREFIX}detail:{identifier}:staff={is_staff}"

    @extend_schema(
        tags=["notify"],
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Log ID",
                required=False,
            ),
            OpenApiParameter(
                name="status",
                type=str,
                description="Filter by status (queued, sent, failed, resend)",
                required=False,
            ),
            OpenApiParameter(
                name="recipient_email",
                type=str,
                description="Filter by recipient email",
                required=False,
            ),
        ],
        responses={200: NotifyLogDisplaySerializer},
        description="Retrieve notification log(s). Staff only.",
    )
    def get(self, request, id=None):
        user = request.user
        if not user.is_staff:
            return _error(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "read"

        try:
            # Single log by id
            if id is not None:
                cache_key = self._get_detail_cache_key(id, user.is_staff)
                cached_data = cache.get(cache_key)

                if cached_data is not None:
                    # Cache hit
                    log_audit_event(
                        request=request,
                        user=user,
                        action_type=action_type,
                        model_name="NotifyLog",
                        object_id=str(id),
                        changes={"detail": "Log retrieved (cached)"},
                        ip_address=client_ip,
                        user_agent=user_agent,
                    )
                    return _success(cached_data, status=status.HTTP_200_OK)

                # Cache miss
                obj = self.get_queryset().get(pk=id)
                serializer = NotifyLogDisplaySerializer(
                    obj, context={"request": request}
                )
                data = serializer.data
                cache.set(cache_key, data, timeout=CACHE_TTL)

                log_audit_event(
                    request=request,
                    user=user,
                    action_type=action_type,
                    model_name="NotifyLog",
                    object_id=str(obj.id),
                    changes={"detail": "Log retrieved"},
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return _success(data, status=status.HTTP_200_OK)

            # List view
            cache_key = self._get_list_cache_key(request)
            cached_response = cache.get(cache_key)

            if cached_response is not None:
                # Cache hit
                log_audit_event(
                    request=request,
                    user=user,
                    action_type=action_type,
                    model_name="NotifyLog",
                    object_id="multiple",
                    changes={"count": cached_response.get("count", 0), "cached": True},
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return Response(cached_response, status=status.HTTP_200_OK)

            # Cache miss: build queryset and paginate
            qs = self.get_queryset()
            status_filter = request.query_params.get("status")
            recipient_email = request.query_params.get("recipient_email")

            if status_filter:
                qs = qs.filter(status=status_filter)
            if recipient_email:
                qs = qs.filter(recipient_email__iexact=recipient_email)

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(qs, request)
            serializer = NotifyLogDisplaySerializer(
                page, many=True, context={"request": request}
            )
            paginated_response = paginator.get_paginated_response(serializer.data)
            response_data = paginated_response.data

            # Cache the response data
            cache.set(cache_key, response_data, timeout=CACHE_TTL)

            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id="multiple",
                changes={"count": len(page) if page else 0},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return paginated_response

        except NotifyLog.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id=str(id) if id else "unknown",
                changes={"error": "Log not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Log not found."}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.exception("NotifyLog retrieval error")
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id=str(id) if id else "multiple",
                changes={"error": str(e)},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "An error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["notify"],
        request=NotifyLogCreateSerializer,
        responses={201: NotifyLogDisplaySerializer},
        description="Create a log entry. Staff only (usually system-generated).",
    )
    def post(self, request):
        user = request.user
        if not user.is_staff:
            return _error(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "create"

        serializer = NotifyLogCreateSerializer(
            data=request.data, context={"request": request}
        )
        try:
            with transaction.atomic():
                serializer.is_valid(raise_exception=True)
                obj = serializer.save()
                self.invalidate_cache()
                log_audit_event(
                    request=request,
                    user=user,
                    action_type=action_type,
                    model_name="NotifyLog",
                    object_id=str(obj.id),
                    changes=serializer.data,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return _success(
                    NotifyLogDisplaySerializer(obj, context={"request": request}).data,
                    status=status.HTTP_201_CREATED,
                )
        except Exception as e:
            logger.error(f"NotifyLog creation failed: {e}")
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id="new",
                changes={"error": str(e), "data": request.data},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["notify"],
        request=NotifyLogCreateSerializer,
        responses={200: NotifyLogDisplaySerializer},
        description="Full update of a log entry. Staff only.",
    )
    def put(self, request, id):
        user = request.user
        if not user.is_staff:
            return _error(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "update"

        try:
            obj = self.get_queryset().get(pk=id)
            original = NotifyLogDisplaySerializer(
                obj, context={"request": request}
            ).data
        except NotifyLog.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id=str(id),
                changes={"error": "Log not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Log not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = NotifyLogCreateSerializer(
            obj, data=request.data, context={"request": request}
        )
        try:
            with transaction.atomic():
                serializer.is_valid(raise_exception=True)
                updated = serializer.save()
                self.invalidate_cache()
                log_audit_event(
                    request=request,
                    user=user,
                    action_type=action_type,
                    model_name="NotifyLog",
                    object_id=str(id),
                    changes={"before": original, "after": serializer.data},
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return _success(
                    NotifyLogDisplaySerializer(
                        updated, context={"request": request}
                    ).data,
                    status=status.HTTP_200_OK,
                )
        except Exception as e:
            logger.error(f"NotifyLog update failed: {e}")
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id=str(id),
                changes={"error": str(e), "data": request.data},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["notify"],
        request=NotifyLogCreateSerializer,
        responses={200: NotifyLogDisplaySerializer},
        description="Partial update of a log entry. Staff only.",
    )
    def patch(self, request, id):
        user = request.user
        if not user.is_staff:
            return _error(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "partial_update"

        try:
            obj = self.get_queryset().get(pk=id)
            original = NotifyLogDisplaySerializer(
                obj, context={"request": request}
            ).data
        except NotifyLog.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id=str(id),
                changes={"error": "Log not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Log not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = NotifyLogCreateSerializer(
            obj, data=request.data, partial=True, context={"request": request}
        )
        try:
            with transaction.atomic():
                serializer.is_valid(raise_exception=True)
                updated = serializer.save()
                self.invalidate_cache()
                log_audit_event(
                    request=request,
                    user=user,
                    action_type=action_type,
                    model_name="NotifyLog",
                    object_id=str(id),
                    changes={
                        "before": original,
                        "after": serializer.data,
                        "modified_fields": list(request.data.keys()),
                    },
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return _success(
                    NotifyLogDisplaySerializer(
                        updated, context={"request": request}
                    ).data,
                    status=status.HTTP_200_OK,
                )
        except Exception as e:
            logger.error(f"NotifyLog partial update failed: {e}")
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id=str(id),
                changes={"error": str(e), "data": request.data},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["notify"],
        responses={204: None},
        description="Delete a log entry. Staff only.",
    )
    def delete(self, request, id):
        user = request.user
        if not user.is_staff:
            return _error(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "delete"

        try:
            with transaction.atomic():
                obj = self.get_queryset().get(pk=id)
                obj_data = NotifyLogDisplaySerializer(
                    obj, context={"request": request}
                ).data
                obj.delete()
                self.invalidate_cache()
                log_audit_event(
                    request=request,
                    user=user,
                    action_type=action_type,
                    model_name="NotifyLog",
                    object_id=str(id),
                    changes={"deleted_log": obj_data},
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return _success(status=status.HTTP_204_NO_CONTENT)
        except NotifyLog.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="NotifyLog",
                object_id=str(id),
                changes={"error": "Log not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Log not found."}, status=status.HTTP_404_NOT_FOUND
            )

    def invalidate_cache(self):
        try:
            cache.delete_pattern(f"{CACHE_PREFIX}*")
        except AttributeError:
            cache.clear()
