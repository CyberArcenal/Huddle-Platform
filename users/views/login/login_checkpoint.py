from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import models
from django.utils import timezone
import logging

from global_utils.response import CustomPagination
from global_utils.security import get_client_ip
from users.models.login_checkpoint import LoginCheckpoint
from users.utils.authentications import IsAuthenticatedAndNotBlacklisted
from users.utils.permissions import is_admin
from users.serializers.checkpoint import (
    LoginCheckpointMinimalSerializer,
    LoginCheckpointDisplaySerializer,
    LoginCheckpointListResponseSerializer,
    LoginCheckpointDetailResponseSerializer,
)
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    OpenApiExample,
)

logger = logging.getLogger(__name__)


# ------------------ LIST VIEW ------------------
@extend_schema(
    tags=["Login Checkpoints"],
    parameters=[
        OpenApiParameter(name="is_used", type=bool, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="is_valid", type=bool, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="search", type=str, location=OpenApiParameter.QUERY),
    ],
    responses={200: LoginCheckpointListResponseSerializer},
    description="Retrieve a paginated list of login checkpoints (minimal serializer).",
)
class LoginCheckpointListView(APIView):
    pagination_class = CustomPagination
    permission_classes = [IsAuthenticatedAndNotBlacklisted]

    def get(self, request):
        user = request.user
        try:
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
                if is_valid.lower() == "true":
                    qs = qs.filter(is_used=False, expires_at__gt=timezone.now())
                else:
                    qs = qs.filter(
                        models.Q(is_used=True) | models.Q(expires_at__lte=timezone.now())
                    )
            if search:
                qs = qs.filter(
                    models.Q(user__username__icontains=search)
                    | models.Q(user__email__icontains=search)
                    | models.Q(token__icontains=search)
                )

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(qs, request)
            serializer = LoginCheckpointMinimalSerializer(page, many=True, context={"request": request})
            return paginator.get_paginated_response(serializer.data)

        except Exception as exc:
            logger.exception("Login checkpoint list retrieval error")
            return Response({"detail": "An error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ------------------ DETAIL VIEW ------------------
@extend_schema(
    tags=["Login Checkpoints"],
    parameters=[
        OpenApiParameter(name="id", type=int, location=OpenApiParameter.PATH),
    ],
    responses={200: LoginCheckpointDetailResponseSerializer, 404: None},
    description="Retrieve full detail of a single login checkpoint by ID.",
    examples=[
        OpenApiExample(
            "Checkpoint detail response",
            value={
                "id": 1,
                "user_data": {"id": 1, "username": "johndoe", "full_name": "John Doe"},
                "token": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                "created_at": "2025-03-08T10:00:00Z",
                "expires_at": "2025-03-08T10:15:00Z",
                "is_used": False,
                "status_display": "Active",
            },
            response_only=True,
        ),
    ],
)
class LoginCheckpointDetailView(APIView):
    permission_classes = [IsAuthenticatedAndNotBlacklisted]

    def get(self, request, id):
        user = request.user
        try:
            checkpoint = LoginCheckpoint.objects.get(pk=id)
        except LoginCheckpoint.DoesNotExist:
            return Response({"message": "Login checkpoint not found."}, status=status.HTTP_404_NOT_FOUND)

        # Permission check
        if not is_admin(user) and checkpoint.user != user:
            return Response({"message": "You do not have permission to view this checkpoint."},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = LoginCheckpointDisplaySerializer(checkpoint, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)