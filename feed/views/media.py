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


class PaginatedMediaSerializer(serializers.Serializer):
    """Matches the structure of paginator.get_paginated_response()"""

    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = MediaDisplaySerializer(many=True)


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
        responses={200: PaginatedMediaSerializer},
        description="List media, optionally filtered by content type, object ID, or by group.",
    )
    def get(self, request):
        content_type_str = request.query_params.get("content_type")
        object_id = request.query_params.get("object_id")
        post_id = request.query_params.get("post_id")
        reel_id = request.query_params.get("reel_id")
        group_id = request.query_params.get("group_id")
        group_content_type = request.query_params.get(
            "group_content_type"
        )  # 'post' or 'reel'
        order_by = request.query_params.get("order_by", "order")

        queryset = Media.objects.all()

        # Shortcut filters take precedence over generic
        if post_id:
            try:
                content_type = ContentType.objects.get(app_label="feed", model="post")
                queryset = queryset.filter(content_type=content_type, object_id=post_id)
            except ContentType.DoesNotExist:
                return Response(
                    {"error": "Post content type not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif reel_id:
            try:
                content_type = ContentType.objects.get(app_label="feed", model="reel")
                queryset = queryset.filter(content_type=content_type, object_id=reel_id)
            except ContentType.DoesNotExist:
                return Response(
                    {"error": "Reel content type not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif group_id:
            # Validate group and permissions
            group = get_object_or_404(Group, id=group_id)
            user = request.user if request.user.is_authenticated else None
            if not GroupService.is_user_allowed_to_view(user, group):
                return Response(
                    {"error": "You do not have permission to view media in this group"},
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
                queryset = queryset.filter(
                    content_type=content_type, object_id=object_id
                )
            except (ValueError, ContentType.DoesNotExist):
                return Response(
                    {"error": "Invalid content_type format. Use 'app_label.model'"},
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
        serializer = MediaDisplaySerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)


class MediaCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MediaDisplaySerializer(required=False, allow_null=True)


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
        serializer = MediaCreateSerializer(
            data=request.data, context={"request": request}
        )

        # Validate without raising so we can return a consistent response shape
        if not serializer.is_valid():
            logger.debug("MediaCreate validation errors: %s", serializer.errors)
            return Response(
                {"status": False, "message": "Invalid media data.", "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Required linking fields
        content_type_str = request.data.get("content_type")
        object_id = request.data.get("object_id")
        if not content_type_str or not object_id:
            return Response(
                {
                    "status": False,
                    "message": "content_type and object_id are required.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse content_type and resolve model
        try:
            app_label, model = content_type_str.split(".")
            content_type = ContentType.objects.get(app_label=app_label, model=model)
        except (ValueError, ContentType.DoesNotExist):
            return Response(
                {
                    "status": False,
                    "message": "Invalid content_type format.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Ensure the content object exists
        try:
            content_object = content_type.get_object_for_this_type(id=object_id)
        except Exception:
            return Response(
                {"status": False, "message": "Content object not found.", "data": None},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Permission check: require ownership when applicable
        if hasattr(content_object, "user") and content_object.user != request.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to add media to this content.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Save media and return consistent response
        try:
            media = serializer.save(
                content_type=content_type,
                object_id=object_id,
                created_by=request.user,
            )
            return Response(
                {
                    "status": True,
                    "message": "Media uploaded successfully.",
                    "data": MediaDisplaySerializer(
                        media, context={"request": request}
                    ).data,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception(
                "Failed to save media for content %s: %s", content_type_str, e
            )
            return Response(
                {"status": False, "message": "Failed to save media.", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MediaDetailView(APIView):
    """
    Retrieve, update, or delete a specific media instance.
    """

    permission_classes = [IsAuthenticated, IsMediaOwner]

    def get_object(self, media_id):
        return get_object_or_404(Media, id=media_id)

    @extend_schema(
        tags=["Media"],
        responses={200: MediaDisplaySerializer},
        description="Get a single media by ID.",
    )
    def get(self, request, media_id):
        media = self.get_object(media_id)
        serializer = MediaDisplaySerializer(media, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["Media"],
        request=MediaCreateSerializer,
        responses={200: MediaDisplaySerializer},
        description="Update media metadata (e.g., order, metadata field).",
    )
    def put(self, request, media_id):
        media = self.get_object(media_id)
        serializer = MediaCreateSerializer(
            media, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            # Prevent changing content_type/object_id? We'll ignore them if provided.
            # Only update allowed fields (file, order, metadata) – but serializer includes file.
            # For safety, we might use a separate update serializer.
            # Here we use MediaCreateSerializer which includes file; but we may not want to allow changing file.
            # We'll create a separate serializer for update.
            updated = serializer.save()
            return Response(
                MediaDisplaySerializer(updated, context={"request": request}).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["Media"],
        responses={204: None},
        description="Delete a media instance.",
    )
    def delete(self, request, media_id):
        media = self.get_object(media_id)
        media.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
