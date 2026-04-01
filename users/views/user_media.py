import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.shortcuts import get_object_or_404
from global_utils.pagination import StandardResultsSetPagination
from users.models import User
from users.serializers.user_image import UserMediaItemSerializer
from users.services.user_image import UserImageService

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class UserMediaGridData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserMediaItemSerializer(many=True)


class UserMediaGridResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserMediaGridData()


# ----------------------------------------------------------------------
# View
# ----------------------------------------------------------------------

class UserMediaGridView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["User Media"],
        parameters=[
            OpenApiParameter(name="page", type=int, description="Page number", required=False),
            OpenApiParameter(name="page_size", type=int, description="Items per page", required=False),
        ],
        responses={200: UserMediaGridResponseSerializer},
        description="Get all media (post images/videos, reels, story media) from a user, paginated.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id is None:
                if not request.user.is_authenticated:
                    return Response(
                        {
                            "status": False,
                            "message": "Authentication required",
                            "data": None,
                        },
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
                target_user = request.user
            else:
                target_user = get_object_or_404(User, id=user_id)

            # Get pagination parameters from request
            paginator = StandardResultsSetPagination()
            try:
                page_num = int(request.query_params.get("page", 1))
                page_size = int(request.query_params.get("page_size", paginator.page_size))
                page_size = min(page_size, paginator.max_page_size)
            except ValueError:
                page_num = 1
                page_size = paginator.page_size

            # Fetch media (service does offset/limit internally)
            items, total = UserImageService.get_user_media(
                user=target_user,
                requester=request.user if request.user.is_authenticated else None,
                request=request,
                page=page_num,
                page_size=page_size,
            )

            # Build paginated data (matches UserMediaGridData)
            base_url = request.build_absolute_uri(request.path)
            query_params = request.query_params.copy()
            query_params.pop("page", None)

            def get_page_link(page_num):
                qs = query_params.copy()
                qs["page"] = page_num
                return f"{base_url}?{qs.urlencode()}"

            next_page = page_num + 1 if (page_num * page_size) < total else None
            prev_page = page_num - 1 if page_num > 1 else None

            data = {
                "page": page_num,
                "hasNext": next_page is not None,
                "hasPrev": prev_page is not None,
                "count": total,
                "next": get_page_link(next_page) if next_page else None,
                "previous": get_page_link(prev_page) if prev_page else None,
                "results": UserMediaItemSerializer(items, many=True, context={"request": request}).data,
            }

            return Response(
                {
                    "status": True,
                    "message": "User media retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user media")
            return Response(
                {
                    "status": False,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )