import logging
from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q, Subquery
from feed.models import Media
from feed.models.post import Post
from django.db import transaction
from feed.models.reel import Reel
from feed.permission.media import IsMediaOwner
from feed.serializers.media import (
    MediaDisplaySerializer,
    MediaCreateSerializer,
    MediaMinimalSerializer,
)
from groups.models.group import Group
from groups.services.group import GroupService
from rest_framework import serializers

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class PaginatedMediaSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = MediaDisplaySerializer(many=True)


class MediaListResponseData(serializers.Serializer):
    pagination = PaginatedMediaSerializer()


class MediaListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MediaListResponseData(allow_null=True)


class MediaCreateResponseData(serializers.Serializer):
    media = MediaDisplaySerializer()


class MediaCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MediaCreateResponseData(allow_null=True)


class MediaDetailResponseData(serializers.Serializer):
    media = MediaDisplaySerializer()


class MediaDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MediaDetailResponseData(allow_null=True)


class MediaUpdateResponseData(serializers.Serializer):
    media = MediaDisplaySerializer()


class MediaUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MediaUpdateResponseData(allow_null=True)


class MediaDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_data(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedMediaSerializer.
    """
    serializer = MediaDisplaySerializer(page, many=True, context={'request': request})
    data = {
        'page': paginator.page.number,
        'hasNext': paginator.page.has_next(),
        'hasPrev': paginator.page.has_previous(),
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class MediaListView(APIView):
    permission_classes = [IsAuthenticated]  # optional, but we'll check for group access

    @extend_schema(
        tags=["Media"],
        parameters=[
            OpenApiParameter(
                name="content_type",
                type=str,
                description="Content type (e.g., 'feed.post', 'feed.reel')",
                required=False,
            ),
            OpenApiParameter(
                name="object_id",
                type=int,
                description="Object ID",
                required=False,
            ),
            OpenApiParameter(
                name="post_id",
                type=int,
                description="Filter by post ID (shortcut for content_type='feed.post')",
                required=False,
            ),
            OpenApiParameter(
                name="reel_id",
                type=int,
                description="Filter by reel ID (shortcut for content_type='feed.reel')",
                required=False,
            ),
            OpenApiParameter(
                name="group_id",
                type=int,
                description="Filter by group ID – returns all media from posts/reels in that group",
                required=False,
            ),
            OpenApiParameter(
                name="group_content_type",
                type=str,
                description="When group_id is given, restrict to this content type (e.g., 'post', 'reel')",
                required=False,
            ),
            OpenApiParameter(
                name="order_by",
                type=str,
                description="Order by field (e.g., 'order', '-created_at')",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                description="Page number",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Items per page",
                required=False,
            ),
        ],
        responses={200: MediaListResponseSerializer},
        description="List media, optionally filtered by content type, object ID, or by group.",
    )
    def get(self, request):
        content_type_str = request.query_params.get("content_type")
        object_id = request.query_params.get("object_id")
        post_id = request.query_params.get("post_id")
        reel_id = request.query_params.get("reel_id")
        group_id = request.query_params.get("group_id")
        group_content_type = request.query_params.get("group_content_type")
        order_by = request.query_params.get("order_by", "order")

        queryset = Media.objects.all()

        # Shortcut filters take precedence over generic
        try:
            if post_id:
                content_type = ContentType.objects.get(app_label="feed", model="post")
                queryset = queryset.filter(content_type=content_type, object_id=post_id)
            elif reel_id:
                content_type = ContentType.objects.get(app_label="feed", model="reel")
                queryset = queryset.filter(content_type=content_type, object_id=reel_id)
            elif group_id:
                # Validate group and permissions
                group = get_object_or_404(Group, id=group_id)
                user = request.user if request.user.is_authenticated else None
                if not GroupService.is_user_allowed_to_view(user, group):
                    return Response(
                        {
                            "status": False,
                            "message": "You do not have permission to view media in this group",
                            "data": None,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                # Get content types for Post and Reel
                post_ct = ContentType.objects.get(app_label="feed", model="post")
                reel_ct = ContentType.objects.get(app_label="feed", model="reel")

                # Build subqueries for object IDs belonging to the group
                post_ids_sub = Post.objects.filter(group=group).values("id")
                reel_ids_sub = Reel.objects.filter(group=group).values("id")

                # Apply content type filter if provided
                if group_content_type == "post":
                    queryset = queryset.filter(
                        content_type=post_ct, object_id__in=Subquery(post_ids_sub)
                    )
                elif group_content_type == "reel":
                    queryset = queryset.filter(
                        content_type=reel_ct, object_id__in=Subquery(reel_ids_sub)
                    )
                else:
                    queryset = queryset.filter(
                        Q(content_type=post_ct, object_id__in=Subquery(post_ids_sub))
                        | Q(content_type=reel_ct, object_id__in=Subquery(reel_ids_sub))
                    )
            elif content_type_str and object_id:
                try:
                    app_label, model = content_type_str.split(".")
                    content_type = ContentType.objects.get(app_label=app_label, model=model)
                    queryset = queryset.filter(content_type=content_type, object_id=object_id)
                except (ValueError, ContentType.DoesNotExist):
                    return Response(
                        {
                            "status": False,
                            "message": "Invalid content_type format. Use 'app_label.model'",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Apply ordering
            valid_order_fields = ["order", "-order", "created_at", "-created_at"]
            if order_by in valid_order_fields:
                queryset = queryset.order_by(order_by)
            else:
                queryset = queryset.order_by("order")  # default

            # Paginate
            from global_utils.pagination import StandardResultsSetPagination

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(queryset, request)
            paginated_data = wrap_paginated_data(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Media list retrieved.",
                    "data": {"pagination": paginated_data},
                }
            )

        except Exception as e:
            logger.exception("Error listing media")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MediaCreateView(APIView):
    """
    Create a new media instance (standalone upload). Typically used for
    adding media to existing content after the fact.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Media"],
        request={
            "multipart/form-data": MediaCreateSerializer,
        },
        responses={
            201: MediaCreateResponseSerializer,
            400: MediaCreateResponseSerializer,
            403: MediaCreateResponseSerializer,
            404: MediaCreateResponseSerializer,
        },
        description="Upload a new media file. The content_type and object_id must be provided to link it to an existing content object.",
    )
    @transaction.atomic
    def post(self, request):
        # Temporarily disabled endpoint (kept for testing)
        return Response(
            {
                "status": False,
                "message": "This endpoint is currently disabled for testing. Use MediaCreateSerializer directly with your content objects.",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

        # (Original code commented out for now; kept for reference)
        # serializer = MediaCreateSerializer(
        #     data=request.data, context={"request": request}
        # )
        # if not serializer.is_valid():
        #     logger.debug("MediaCreate validation errors: %s", serializer.errors)
        #     return Response(
        #         {"status": False, "message": "Invalid media data.", "data": None},
        #         status=status.HTTP_400_BAD_REQUEST,
        #     )
        # ... rest of the implementation


class MediaDetailView(APIView):
    """
    Retrieve, update, or delete a specific media instance.
    """

    permission_classes = [IsAuthenticated, IsMediaOwner]

    def get_object(self, media_id):
        return get_object_or_404(Media, id=media_id)

    @extend_schema(
        tags=["Media"],
        responses={200: MediaDetailResponseSerializer},
        description="Get a single media by ID.",
    )
    def get(self, request, media_id):
        try:
            media = self.get_object(media_id)
            data = MediaDisplaySerializer(media, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Media retrieved.",
                    "data": {"media": data},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving media %s", media_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Media"],
        request=MediaCreateSerializer,
        responses={200: MediaUpdateResponseSerializer},
        description="Update media metadata (e.g., order, metadata field).",
    )
    def put(self, request, media_id):
        try:
            media = self.get_object(media_id)
            serializer = MediaCreateSerializer(
                media, data=request.data, partial=True, context={"request": request}
            )
            if serializer.is_valid():
                updated = serializer.save()
                data = MediaDisplaySerializer(updated, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Media updated successfully.",
                        "data": {"media": data},
                    }
                )
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error updating media %s", media_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Media"],
        responses={204: MediaDeleteResponseSerializer},
        description="Delete a media instance.",
    )
    def delete(self, request, media_id):
        try:
            media = self.get_object(media_id)
            media.delete()
            return Response(
                {
                    "status": True,
                    "message": "Media deleted successfully.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        except Exception as e:
            logger.exception("Error deleting media %s", media_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )