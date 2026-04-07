# users/views/otp_requests.py
import logging
from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import serializers
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter

from global_utils.pagination import UsersPagination
from global_utils.security import get_client_ip
from users.models import OtpRequest
from users.serializers.otp import (
    OtpRequestMinimalSerializer,
    OtpRequestDisplaySerializer,
)
from users.utils.authentications import IsAuthenticatedAndNotBlacklisted
from users.utils.permissions import IsAccountActive, is_admin

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for drf-spectacular
# ----------------------------------------------------------------------

class PaginatedOtpRequestData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = OtpRequestMinimalSerializer(many=True)


class OtpRequestListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedOtpRequestData()


class OtpRequestDetailResponseData(serializers.Serializer):
    # Use the existing display serializer fields
    id = serializers.IntegerField()
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    email = serializers.EmailField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    otp_code = serializers.CharField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    is_used = serializers.BooleanField()
    attempt_count = serializers.IntegerField()
    type = serializers.CharField()
    is_email_delivered = serializers.BooleanField()
    is_phone_delivered = serializers.BooleanField()


class OtpRequestDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = OtpRequestDetailResponseData()


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------

def wrap_paginated_otp_requests(paginator, page, request):
    """
    Construct a paginated data dict for OtpRequestMinimalSerializer.
    """
    serializer = OtpRequestMinimalSerializer(page, many=True, context={"request": request})
    data = {
        "page": paginator.page.number,
        "hasNext": paginator.page.has_next(),
        "hasPrev": paginator.page.has_previous(),
        "count": paginator.page.paginator.count,
        "next": paginator.get_next_link(),
        "previous": paginator.get_previous_link(),
        "results": serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class OtpRequestListView(APIView):
    """
    Retrieve a paginated list of OTP requests (minimal data).
    Admins see all; regular users see only their own.
    """
    permission_classes = [IsAuthenticatedAndNotBlacklisted, IsAccountActive]
    pagination_class = UsersPagination

    @extend_schema(
        tags=["OTP Requests"],
        parameters=[
            OpenApiParameter(
                name="email",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by email (icontains)",
                required=False,
            ),
            OpenApiParameter(
                name="is_used",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by used status",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search in email or OTP code",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: OtpRequestListResponseSerializer},
        description="Retrieve a paginated list of OTP requests.",
    )
    def get(self, request):
        user = request.user

        try:
            if is_admin(user):
                qs = OtpRequest.objects.all().order_by("-created_at")
            else:
                qs = OtpRequest.objects.filter(user=user).order_by("-created_at")

            # Apply filters
            email = request.query_params.get("email")
            is_used = request.query_params.get("is_used")
            search = request.query_params.get("search")

            if email:
                qs = qs.filter(email__icontains=email)
            if is_used is not None:
                qs = qs.filter(is_used=is_used.lower() == "true")
            if search:
                qs = qs.filter(
                    models.Q(email__icontains=search) |
                    models.Q(otp_code__icontains=search)
                )

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(qs, request)
            paginated_data = wrap_paginated_otp_requests(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "OTP requests retrieved successfully.",
                    "data": paginated_data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("OtpRequestListView error")
            return Response(
                {
                    "status": False,
                    "message": "An error occurred while retrieving OTP requests.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class OtpRequestDetailView(APIView):
    """
    Retrieve full detail of a single OTP request by ID.
    """
    permission_classes = [IsAuthenticatedAndNotBlacklisted, IsAccountActive]

    @extend_schema(
        tags=["OTP Requests"],
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                description="OTP request ID",
                required=True,
            ),
        ],
        responses={200: OtpRequestDetailResponseSerializer, 403: None, 404: None},
        description="Retrieve full detail of a single OTP request by ID.",
    )
    def get(self, request, id):
        user = request.user

        try:
            otp_request = OtpRequest.objects.get(pk=id)
        except OtpRequest.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "OTP request not found.",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Permission check
        if not is_admin(user) and otp_request.user != user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view this OTP request.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OtpRequestDisplaySerializer(otp_request, context={"request": request})

        return Response(
            {
                "status": True,
                "message": "OTP request retrieved successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )