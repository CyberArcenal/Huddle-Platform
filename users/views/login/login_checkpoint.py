# users/views/login_checkpoint.py
import logging
from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import serializers
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    OpenApiExample,
)

from global_utils.pagination import UsersPagination
from global_utils.security import get_client_ip
from users.models.login_checkpoint import LoginCheckpoint
from users.utils.authentications import IsAuthenticatedAndNotBlacklisted
from users.utils.permissions import is_admin
from users.serializers.checkpoint import (
    LoginCheckpointMinimalSerializer,
    LoginCheckpointDisplaySerializer,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for drf-spectacular
# ----------------------------------------------------------------------

class PaginatedLoginCheckpointData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = LoginCheckpointMinimalSerializer(many=True)


class LoginCheckpointListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedLoginCheckpointData()


class LoginCheckpointDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LoginCheckpointDisplaySerializer()


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------

def wrap_paginated_checkpoints(paginator, page, request):
    """
    Construct a paginated data dict for LoginCheckpointMinimalSerializer.
    """
    serializer = LoginCheckpointMinimalSerializer(page, many=True, context={"request": request})
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

class LoginCheckpointListView(APIView):
    """
    Retrieve a paginated list of login checkpoints (minimal data).
    Admins see all; regular users see only their own.
    """
    permission_classes = [IsAuthenticatedAndNotBlacklisted]
    pagination_class = UsersPagination

    @extend_schema(
        tags=["Login Checkpoints"],
        parameters=[
            OpenApiParameter(
                name="is_used",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by used status (true/false)",
                required=False,
            ),
            OpenApiParameter(
                name="is_valid",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by validity (true = not used and not expired)",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search in username, email, or token",
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
        responses={200: LoginCheckpointListResponseSerializer},
        description="Retrieve a paginated list of login checkpoints (minimal serializer).",
    )
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

            if is_used is not None:
                qs = qs.filter(is_used=is_used.lower() == "true")
            if is_valid is not None:
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
            paginated_data = wrap_paginated_checkpoints(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Login checkpoints retrieved successfully.",
                    "data": paginated_data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("LoginCheckpointListView error")
            return Response(
                {
                    "status": False,
                    "message": "An error occurred while retrieving login checkpoints.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LoginCheckpointDetailView(APIView):
    """
    Retrieve full detail of a single login checkpoint by ID.
    """
    permission_classes = [IsAuthenticatedAndNotBlacklisted]

    @extend_schema(
        tags=["Login Checkpoints"],
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Login checkpoint ID",
                required=True,
            ),
        ],
        responses={200: LoginCheckpointDetailResponseSerializer, 403: None, 404: None},
        description="Retrieve full detail of a single login checkpoint by ID.",
        examples=[
            OpenApiExample(
                "Checkpoint detail response",
                value={
                    "status": True,
                    "message": "Login checkpoint retrieved successfully.",
                    "data": {
                        "id": 1,
                        "user_data": {"id": 1, "username": "johndoe", "full_name": "John Doe"},
                        "token": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                        "created_at": "2025-03-08T10:00:00Z",
                        "expires_at": "2025-03-08T10:15:00Z",
                        "is_used": False,
                        "status_display": "Active",
                    },
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request, id):
        user = request.user

        try:
            checkpoint = LoginCheckpoint.objects.get(pk=id)
        except LoginCheckpoint.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Login checkpoint not found.",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Permission check
        if not is_admin(user) and checkpoint.user != user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view this checkpoint.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = LoginCheckpointDisplaySerializer(checkpoint, context={"request": request})

        return Response(
            {
                "status": True,
                "message": "Login checkpoint retrieved successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )