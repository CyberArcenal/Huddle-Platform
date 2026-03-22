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

from notifications.models.email_template import EmailTemplate
from notifications.serializers.email_template import (
    EmailTemplateCreateSerializer,
    EmailTemplateDisplaySerializer,
)

# Constants for caching
CACHE_TTL = 60 * 60 * 24  # 5 minutes
CACHE_PREFIX = "api:emailtemplate:"

logger = logging.getLogger(__name__)


class EmailTemplateCRUD(APIView):
    pagination_class = CustomPagination

    def get_queryset(self):
        # Only staff can access email templates
        if self.request.user.is_staff:
            return EmailTemplate.objects.all()
        return EmailTemplate.objects.none()

    def _get_list_cache_key(self, request):
        """Generate cache key for email template list based on full path and staff status."""
        path = request.get_full_path()
        return f"{CACHE_PREFIX}list:staff={request.user.is_staff}:{path}"

    def _get_detail_cache_key(self, identifier, is_staff):
        """Generate cache key for a single email template (by id)."""
        return f"{CACHE_PREFIX}detail:{identifier}:staff={is_staff}"

    @extend_schema(
        tags=["email template's"],
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Template ID",
                required=False,
            ),
            OpenApiParameter(
                name="name",
                type=str,
                description="Filter by template name (choice)",
                required=False,
            ),
        ],
        responses={200: EmailTemplateDisplaySerializer},
        description="List email templates. Staff only.",
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
            # Single template by id
            if id is not None:
                cache_key = self._get_detail_cache_key(id, user.is_staff)
                cached_data = cache.get(cache_key)

                if cached_data is not None:
                    # Cache hit
                    log_audit_event(
                        request=request,
                        user=user,
                        action_type=action_type,
                        model_name="EmailTemplate",
                        object_id=str(id),
                        changes={"detail": "Template retrieved (cached)"},
                        ip_address=client_ip,
                        user_agent=user_agent,
                    )
                    return _success(cached_data, status=status.HTTP_200_OK)

                # Cache miss
                obj = self.get_queryset().get(pk=id)
                serializer = EmailTemplateDisplaySerializer(
                    obj, context={"request": request}
                )
                data = serializer.data
                cache.set(cache_key, data, timeout=CACHE_TTL)

                log_audit_event(
                    request=request,
                    user=user,
                    action_type=action_type,
                    model_name="EmailTemplate",
                    object_id=str(obj.id),
                    changes={"detail": "Template retrieved"},
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
                    model_name="EmailTemplate",
                    object_id="multiple",
                    changes={"count": cached_response.get("count", 0), "cached": True},
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                # Return as DRF Response to preserve pagination structure
                return Response(cached_response, status=status.HTTP_200_OK)

            # Cache miss: build queryset and paginate
            qs = self.get_queryset()
            name = request.query_params.get("name")
            if name:
                qs = qs.filter(name=name)

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(qs, request)
            serializer = EmailTemplateDisplaySerializer(
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
                model_name="EmailTemplate",
                object_id="multiple",
                changes={"count": len(page) if page else 0},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return paginated_response

        except EmailTemplate.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="EmailTemplate",
                object_id=str(id) if id else "unknown",
                changes={"error": "Template not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.exception("EmailTemplate retrieval error")
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="EmailTemplate",
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
        tags=["email template's"],
        request=EmailTemplateCreateSerializer,
        responses={201: EmailTemplateDisplaySerializer},
        description="Create an email template. Staff only.",
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

        serializer = EmailTemplateCreateSerializer(
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
                    model_name="EmailTemplate",
                    object_id=str(obj.id),
                    changes=serializer.data,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return _success(
                    EmailTemplateDisplaySerializer(
                        obj, context={"request": request}
                    ).data,
                    status=status.HTTP_201_CREATED,
                )
        except Exception as e:
            logger.error(f"EmailTemplate creation failed: {e}")
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="EmailTemplate",
                object_id="new",
                changes={"error": str(e), "data": request.data},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["email template's"],
        request=EmailTemplateCreateSerializer,
        responses={200: EmailTemplateDisplaySerializer},
        description="Full update of an email template. Staff only.",
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
            original = EmailTemplateDisplaySerializer(
                obj, context={"request": request}
            ).data
        except EmailTemplate.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="EmailTemplate",
                object_id=str(id),
                changes={"error": "Template not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = EmailTemplateCreateSerializer(
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
                    model_name="EmailTemplate",
                    object_id=str(id),
                    changes={"before": original, "after": serializer.data},
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return _success(
                    EmailTemplateDisplaySerializer(
                        updated, context={"request": request}
                    ).data,
                    status=status.HTTP_200_OK,
                )
        except Exception as e:
            logger.error(f"EmailTemplate update failed: {e}")
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="EmailTemplate",
                object_id=str(id),
                changes={"error": str(e), "data": request.data},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["email template's"],
        request=EmailTemplateCreateSerializer,
        responses={200: EmailTemplateDisplaySerializer},
        description="Partial update of an email template. Staff only.",
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
            original = EmailTemplateDisplaySerializer(
                obj, context={"request": request}
            ).data
        except EmailTemplate.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="EmailTemplate",
                object_id=str(id),
                changes={"error": "Template not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = EmailTemplateCreateSerializer(
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
                    model_name="EmailTemplate",
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
                    EmailTemplateDisplaySerializer(
                        updated, context={"request": request}
                    ).data,
                    status=status.HTTP_200_OK,
                )
        except Exception as e:
            logger.error(f"EmailTemplate partial update failed: {e}")
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="EmailTemplate",
                object_id=str(id),
                changes={"error": str(e), "data": request.data},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["email template's"],
        responses={204: None},
        description="Delete an email template. Staff only.",
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
                obj_data = EmailTemplateDisplaySerializer(
                    obj, context={"request": request}
                ).data
                obj.delete()
                self.invalidate_cache()
                log_audit_event(
                    request=request,
                    user=user,
                    action_type=action_type,
                    model_name="EmailTemplate",
                    object_id=str(id),
                    changes={"deleted_template": obj_data},
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                return _success(status=status.HTTP_204_NO_CONTENT)
        except EmailTemplate.DoesNotExist:
            log_audit_event(
                request=request,
                user=user,
                action_type=action_type,
                model_name="EmailTemplate",
                object_id=str(id),
                changes={"error": "Template not found"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            return _error(
                {"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND
            )

    def invalidate_cache(self):
        try:
            # Clear all cache keys with our prefix
            cache.delete_pattern(f"{CACHE_PREFIX}*")
        except AttributeError:
            # Fallback for backends that don't support delete_pattern
            cache.clear()
