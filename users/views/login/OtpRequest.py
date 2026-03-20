import logging
from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from global_utils.response import CustomPagination
from global_utils.security import get_client_ip
from users.models import OtpRequest
from users.serializers.otp import (
    OtpRequestMinimalSerializer,
    OtpRequestDisplaySerializer,
    OtpRequestListResponseSerializer,
)
from users.utils.authentications import IsAuthenticatedAndNotBlacklisted
from users.utils.permissions import IsAccountActive, is_admin
from drf_spectacular.utils import extend_schema, OpenApiParameter

logger = logging.getLogger(__name__)


# ------------------ LIST VIEW ------------------
@extend_schema(
    tags=['OTP Requests'],
    parameters=[
        OpenApiParameter(name='email', type=str, location=OpenApiParameter.QUERY, description='Filter by email'),
        OpenApiParameter(name='is_used', type=bool, location=OpenApiParameter.QUERY, description='Filter by used status'),
        OpenApiParameter(name='search', type=str, location=OpenApiParameter.QUERY, description='Search in email or OTP code'),
    ],
    responses={200: OtpRequestListResponseSerializer},
    description="Retrieve a paginated list of OTP requests (minimal serializer).",
)
class OtpRequestListView(APIView):
    pagination_class = CustomPagination
    permission_classes = [IsAuthenticatedAndNotBlacklisted, IsAccountActive]

    def get(self, request):
        user = request.user
        try:
            if is_admin(user):
                qs = OtpRequest.objects.all().order_by('-created_at')
            else:
                qs = OtpRequest.objects.filter(user=user).order_by('-created_at')

            # Apply filters
            email = request.query_params.get('email')
            is_used = request.query_params.get('is_used')
            search = request.query_params.get('search')

            if email:
                qs = qs.filter(email__icontains=email)
            if is_used:
                qs = qs.filter(is_used=is_used.lower() == 'true')
            if search:
                qs = qs.filter(
                    models.Q(email__icontains=search) |
                    models.Q(otp_code__icontains=search)
                )

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(qs, request)
            serializer = OtpRequestMinimalSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        except Exception as exc:
            logger.exception('OTP request list retrieval error')
            return Response({'detail': 'An error occurred.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ------------------ DETAIL VIEW ------------------
@extend_schema(
    tags=['OTP Requests'],
    parameters=[
        OpenApiParameter(name='id', type=int, location=OpenApiParameter.PATH, description='OTP request ID'),
    ],
    responses={200: OtpRequestDisplaySerializer, 404: None},
    description="Retrieve full detail of a single OTP request by ID.",
)
class OtpRequestDetailView(APIView):
    permission_classes = [IsAuthenticatedAndNotBlacklisted, IsAccountActive]

    def get(self, request, id):
        user = request.user
        try:
            otp_request = OtpRequest.objects.get(pk=id)
        except OtpRequest.DoesNotExist:
            return Response({'message': 'OTP request not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Permission check
        if not is_admin(user) and otp_request.user != user:
            return Response({'message': 'You do not have permission to view this OTP request.'},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = OtpRequestDisplaySerializer(otp_request, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)