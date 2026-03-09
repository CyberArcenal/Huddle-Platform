# accounts/views/login_checkpoint_crud.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import models
import logging
from global_utils.response import CustomPagination
from global_utils.security import get_client_ip
from django.utils import timezone
from django.db import transaction
from users.utils.authentications import IsAuthenticatedAndNotBlacklisted
from users.models.base import LoginCheckpoint, User
from users.serializers.checkpoint import LoginCheckpointSerializer
from users.utils.permissions import is_admin
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
                description="Checkpoint ID (optional)",
            ),
            OpenApiParameter(
                name="is_used",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by used status",
            ),
            OpenApiParameter(
                name="is_valid",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by validity",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search in username, email, token",
            ),
        ],
        responses={200: LoginCheckpointSerializer(many=True)},
        description="Retrieve a list of login checkpoints or a single checkpoint by ID.",
        examples=[
            OpenApiExample(
                "Checkpoint detail response",
                value={
                    "id": 1,
                    "user_data": {
                        "id": 1,
                        "username": "johndoe",
                        "full_name": "John Doe",
                    },
                    "token": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                    "created_at": "2025-03-08T10:00:00Z",
                    "expires_at": "2025-03-08T10:15:00Z",
                    "is_used": False,
                    "status_display": "Active",
                },
                response_only=True,
            ),
        ],
    ),
    post=extend_schema(
        request=LoginCheckpointSerializer,
        responses={201: LoginCheckpointSerializer},
        description="Create a new login checkpoint.",
        examples=[
            OpenApiExample(
                "Create checkpoint request",
                value={"user": 1},
                request_only=True,
            ),
            OpenApiExample(
                "Create checkpoint response",
                value={
                    "id": 2,
                    "user_data": {
                        "id": 1,
                        "username": "johndoe",
                        "full_name": "John Doe",
                    },
                    "token": "b2c3d4e5-f6g7-8901-2345-67890abcdef1",
                    "created_at": "2025-03-08T11:00:00Z",
                    "expires_at": "2025-03-08T11:15:00Z",
                    "is_used": False,
                    "status_display": "Active",
                },
                response_only=True,
            ),
        ],
    ),
    # similarly for put, patch, delete...
)
class LoginCheckpointCRUD(APIView):
    pagination_class = CustomPagination
    permission_classes = [
        IsAuthenticatedAndNotBlacklisted,
    ]

    def get(self, request, id=None):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "read"

        try:
            if id is not None:
                try:
                    checkpoint = LoginCheckpoint.objects.get(pk=id)
                except LoginCheckpoint.DoesNotExist:
                    return Response(
                        {"message": "Login checkpoint not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # Check if user has permission to view this checkpoint
                if not is_admin(user) and checkpoint.user != user:
                    return Response(
                        {
                            "message": "You do not have permission to view this login checkpoint."
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                serializer = LoginCheckpointSerializer(
                    checkpoint, context={"request": request}
                )

                return Response(serializer.data, status=status.HTTP_200_OK)

            # List login checkpoints with filters
            if is_admin(user):
                qs = LoginCheckpoint.objects.all().order_by("-created_at")
            else:
                qs = LoginCheckpoint.objects.filter(user=user).order_by("-created_at")

            # Apply filters
            is_used = request.query_params.get("is_used")
            is_valid = request.query_params.get("is_valid")
            search = request.query_params.get("search")

            if is_used:
                qs = qs.filter(is_used=is_used.lower() == "true")
            if is_valid:
                # Filter by validity (not expired and not used)
                if is_valid.lower() == "true":
                    qs = qs.filter(is_used=False, expires_at__gt=timezone.now())
                else:
                    qs = qs.filter(
                        models.Q(is_used=True)
                        | models.Q(expires_at__lte=timezone.now())
                    )
            if search:
                qs = qs.filter(
                    models.Q(user__username__icontains=search)
                    | models.Q(user__email__icontains=search)
                    | models.Q(token__icontains=search)
                )

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(qs, request)
            serializer = LoginCheckpointSerializer(
                page, many=True, context={"request": request}
            )
            response = paginator.get_paginated_response(serializer.data)

            return response

        except LoginCheckpoint.DoesNotExist:

            return Response(
                {"detail": "Login checkpoint not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as exc:
            logger.exception("Login checkpoint retrieval error")
            return Response(
                {"detail": "An error occurred while processing your request."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @transaction.atomic
    def post(self, request):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "create"

        logger.info(f"Login checkpoint creation: {request.data}")

        # If user is not staff, ensure they can only create checkpoints for themselves
        if (
            not is_admin(user)
            and "user" in request.data
            and int(request.data["user"]) != user.id
        ):
            return Response(
                {"detail": "You can only create login checkpoints for yourself."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = LoginCheckpointSerializer(
            data=request.data, context={"request": request}
        )

        try:
            serializer.is_valid(raise_exception=True)
            checkpoint = serializer.save()

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as exc:
            logger.error(f"Login checkpoint creation failed: {exc}")

            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    @transaction.atomic
    def put(self, request, id):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "update"

        try:
            checkpoint = LoginCheckpoint.objects.get(pk=id)

            # Check permissions
            if not is_admin(user) and checkpoint.user != user:
                return Response(
                    {
                        "detail": "You do not have permission to update this login checkpoint."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Store the original data for logging
            original_data = LoginCheckpointSerializer(checkpoint).data
        except LoginCheckpoint.DoesNotExist:

            return Response(
                {"detail": "Login checkpoint not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.info(f"Updating login checkpoint {id}: {request.data}")
        serializer = LoginCheckpointSerializer(
            checkpoint, data=request.data, partial=False, context={"request": request}
        )

        try:
            serializer.is_valid(raise_exception=True)
            updated_checkpoint = serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error(f"Login checkpoint update failed: {exc}")

            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    @transaction.atomic
    def delete(self, request, id):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "delete"

        try:
            checkpoint = LoginCheckpoint.objects.get(pk=id)

            # Check permissions
            if not is_admin(user) and checkpoint.user != user:
                return Response(
                    {
                        "detail": "You do not have permission to delete this login checkpoint."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Store the data for logging before deletion
            checkpoint_data = LoginCheckpointSerializer(checkpoint).data
        except LoginCheckpoint.DoesNotExist:

            return Response(
                {"detail": "Login checkpoint not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Delete the login checkpoint
        checkpoint.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, id):
        user: User = request.user
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        action_type = "partial_update"

        try:
            checkpoint = LoginCheckpoint.objects.get(pk=id)

            # Check permissions
            if not is_admin(user) and checkpoint.user != user:
                return Response(
                    {
                        "detail": "You do not have permission to update this login checkpoint."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Store the original data for logging
            original_data = LoginCheckpointSerializer(checkpoint).data
        except LoginCheckpoint.DoesNotExist:

            return Response(
                {"detail": "Login checkpoint not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.info(f"Partial update for login checkpoint {id}: {request.data}")
        serializer = LoginCheckpointSerializer(
            checkpoint, data=request.data, partial=True, context={"request": request}
        )

        try:
            serializer.is_valid(raise_exception=True)
            updated_checkpoint = serializer.save()

            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error(f"Login checkpoint partial update failed: {exc}")

            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
