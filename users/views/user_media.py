import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.shortcuts import get_object_or_404
from global_utils.pagination import StandardResultsSetPagination
from users.models import User
from users.serializers.user_media import UserMediaItemSerializer
from users.services.user_media import UserMediaService
from rest_framework import serializers
logger = logging.getLogger(__name__)


class UserMediaGridView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    class PaginatedUserMediaGridSerializer(serializers.Serializer):
        """Matches the structure of paginator.get_paginated_response()"""

        page = serializers.IntegerField()
        hasNext = serializers.BooleanField()
        hasPrev = serializers.BooleanField()
        count = serializers.IntegerField()
        next = serializers.URLField(allow_null=True)
        previous = serializers.URLField(allow_null=True)
        results = UserMediaItemSerializer(many=True)

    @extend_schema(
        tags=["User Media"],
        parameters=[
            OpenApiParameter(name="page", type=int, description="Page number", required=False),
            OpenApiParameter(name="page_size", type=int, description="Items per page", required=False),
        ],
        responses={200: PaginatedUserMediaGridSerializer},
        description="Get all media (post images/videos, reels, story media) from a user, paginated.",
    )
    def get(self, request, user_id=None):
        if user_id is None:
            if not request.user.is_authenticated:
                return Response(
                    {"error": "Authentication required"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            target_user = request.user
        else:
            target_user = get_object_or_404(User, id=user_id)

        # Pagination parameters
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(None, request)  # We'll paginate manually

        try:
            page_num = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", paginator.page_size))
            page_size = min(page_size, paginator.max_page_size)
        except ValueError:
            page_num = 1
            page_size = paginator.page_size

        # Fetch media
        items, total = UserMediaService.get_user_media(
            user=target_user,
            page=page_num,
            page_size=page_size,
        )

        # Build paginated response manually (to match BasePagination structure)
        response = {
            "count": total,
            "page": page_num,
            "hasNext": (page_num * page_size) < total,
            "hasPrev": page_num > 1,
            "next": None,  # could generate URL
            "previous": None,
            "results": UserMediaItemSerializer(items, many=True).data,
        }
        return Response(response)