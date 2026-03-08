# accounts/views/otp_request_crud.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import models
import logging
from global_utils.response import CustomPagination
from global_utils.security import get_client_ip
from users.models.base import OtpRequest, User
from users.serializers.otp import OtpRequestSerializer
from users.utils.authentications import IsAuthenticatedAndNotBlacklisted
from users.utils.permissions import IsAccountActive, is_admin
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    OpenApiExample,
    extend_schema_view,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                description="OTP request ID (optional)",
            ),
            OpenApiParameter(
                name="email",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by email",
            ),
            OpenApiParameter(
                name="is_used",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by used status",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search in email, OTP code",
            ),
        ],
        responses={200: OtpRequestSerializer(many=True)},
        description="Retrieve a list of OTP requests or a single request by ID.",
        examples=[
            OpenApiExample(
                "OTP request detail response",
                value={
                    "id": 1,
                    "user_data": {
                        "id": 1,
                        "username": "johndoe",
                        "full_name": "John Doe",
                    },
                    "otp_code": "123456",
                    "email": "john@example.com",
                    "created_at": "2025-03-08T10:00:00Z",
                    "expires_at": "2025-03-08T10:10:00Z",
                    "is_used": False,
                    "attempt_count": 0,
                    "status_display": "Active",
                },
                response_only=True,
            ),
        ],
    ),
    post=extend_schema(
        request=OtpRequestSerializer,
        responses={201: OtpRequestSerializer},
        description="Create a new OTP request.",
        examples=[
            OpenApiExample(
                "Create OTP request",
                value={"user": 1, "otp_code": "123456"},
                request_only=True,
            ),
            OpenApiExample(
                "Create OTP response",
                value={
                    "id": 2,
                    "user_data": {
                        "id": 1,
                        "username": "johndoe",
                        "full_name": "John Doe",
                    },
                    "otp_code": "654321",
                    "email": "john@example.com",
                    "created_at": "2025-03-08T11:00:00Z",
                    "expires_at": "2025-03-08T11:10:00Z",
                    "is_used": False,
                    "attempt_count": 0,
                    "status_display": "Active",
                },
                response_only=True,
            ),
        ],
    ),
    # put, patch, delete similarly...
)
class OtpRequestCRUD(APIView):
    pagination_class = CustomPagination
    permission_classes = [
        IsAuthenticatedAndNotBlacklisted,  # built-in
        IsAccountActive,  # custom: only "active" users
    ]

    def get(self, request, id=None):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "read"

        try:
            if id is not None:
                try:
                    otp_request = OtpRequest.objects.get(pk=id)
                except OtpRequest.DoesNotExist:
                    return Response(
                        {"message": "OTP request not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # Check if user has permission to view this OTP request
                if not is_admin(user) and otp_request.user != user:
                    return Response(
                        {
                            "message": "You do not have permission to view this OTP request."
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                serializer = OtpRequestSerializer(
                    otp_request, context={"request": request}
                )

                return Response(serializer.data, status=status.HTTP_200_OK)

            # List OTP requests with filters
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
            if is_used:
                qs = qs.filter(is_used=is_used.lower() == "true")
            if search:
                qs = qs.filter(
                    models.Q(email__icontains=search)
                    | models.Q(otp_code__icontains=search)
                )

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(qs, request)
            serializer = OtpRequestSerializer(
                page, many=True, context={"request": request}
            )
            response = paginator.get_paginated_response(serializer.data)

            return response

        except OtpRequest.DoesNotExist:

            return Response(
                {"detail": "OTP request not found."}, status=status.HTTP_404_NOT_FOUND
            )

        except Exception as exc:
            logger.exception("OTP request retrieval error")

            return Response(
                {"detail": "An error occurred while processing your request."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "create"

        logger.info(f"OTP request creation: {request.data}")

        # If user is not staff, ensure they can only create OTP requests for themselves
        if (
            not is_admin(user)
            and "user" in request.data
            and int(request.data["user"]) != user.id
        ):
            return Response(
                {"detail": "You can only create OTP requests for yourself."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OtpRequestSerializer(
            data=request.data, context={"request": request}
        )

        try:
            serializer.is_valid(raise_exception=True)
            otp_request = serializer.save()

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as exc:
            logger.error(f"OTP request creation failed: {exc}")

            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, id):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "update"

        try:
            otp_request = OtpRequest.objects.get(pk=id)

            # Check permissions
            if not is_admin(user) and otp_request.user != user:
                return Response(
                    {
                        "detail": "You do not have permission to update this OTP request."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Store the original data for logging
            original_data = OtpRequestSerializer(otp_request).data
        except OtpRequest.DoesNotExist:

            return Response(
                {"detail": "OTP request not found."}, status=status.HTTP_404_NOT_FOUND
            )

        logger.info(f"Updating OTP request {id}: {request.data}")
        serializer = OtpRequestSerializer(
            otp_request, data=request.data, partial=False, context={"request": request}
        )

        try:
            serializer.is_valid(raise_exception=True)
            updated_otp_request = serializer.save()

            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error(f"OTP request update failed: {exc}")

            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "delete"
        if not is_admin(user):
            return Response(
                {"message": "Access denied"}, status=status.HTTP_403_FORBIDDEN
            )
        try:
            otp_request = OtpRequest.objects.get(pk=id)

            # Check permissions
            if not is_admin(user) and otp_request.user != user:
                return Response(
                    {
                        "detail": "You do not have permission to delete this OTP request."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Store the data for logging before deletion
            otp_data = OtpRequestSerializer(otp_request).data
        except OtpRequest.DoesNotExist:

            return Response(
                {"detail": "OTP request not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # Delete the OTP request
        otp_request.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, id):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "partial_update"

        try:
            otp_request = OtpRequest.objects.get(pk=id)

            # Check permissions
            if not is_admin(user) and otp_request.user != user:
                return Response(
                    {
                        "detail": "You do not have permission to update this OTP request."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Store the original data for logging
            original_data = OtpRequestSerializer(otp_request).data
        except OtpRequest.DoesNotExist:

            return Response(
                {"detail": "OTP request not found."}, status=status.HTTP_404_NOT_FOUND
            )

        logger.info(f"Partial update for OTP request {id}: {request.data}")
        serializer = OtpRequestSerializer(
            otp_request, data=request.data, partial=True, context={"request": request}
        )

        try:
            serializer.is_valid(raise_exception=True)
            updated_otp_request = serializer.save()

            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error(f"OTP request partial update failed: {exc}")

            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
