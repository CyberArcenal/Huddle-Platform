# stories/views/highlight.py

from rest_framework.views import APIView, PermissionDenied
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from stories.models import StoryHighlight
from stories.services.highlight import StoryHighlightService
from users.models import User
from stories.serializers.highlight import (
    StoryHighlightSerializer,
    StoryHighlightCreateSerializer,
    StoryHighlightSetCoverSerializer,
    StoryHighlightUpdateSerializer,
    StoryHighlightAddStoriesSerializer,
    StoryHighlightRemoveStoriesSerializer,
)
import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class StoryHighlightListResponseData(serializers.Serializer):
    highlights = StoryHighlightSerializer(many=True)


class StoryHighlightListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryHighlightListResponseData()


class StoryHighlightCreateResponseData(serializers.Serializer):
    highlight = StoryHighlightSerializer()


class StoryHighlightCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryHighlightCreateResponseData()


class StoryHighlightDetailResponseData(serializers.Serializer):
    highlight = StoryHighlightSerializer()


class StoryHighlightDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryHighlightDetailResponseData()


class StoryHighlightUpdateResponseData(serializers.Serializer):
    highlight = StoryHighlightSerializer()


class StoryHighlightUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryHighlightUpdateResponseData()


class StoryHighlightDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class StoryHighlightAddStoriesResponseData(serializers.Serializer):
    highlight = StoryHighlightSerializer()


class StoryHighlightAddStoriesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryHighlightAddStoriesResponseData()


class StoryHighlightRemoveStoriesResponseData(serializers.Serializer):
    highlight = StoryHighlightSerializer()


class StoryHighlightRemoveStoriesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryHighlightRemoveStoriesResponseData()


class StoryHighlightSetCoverResponseData(serializers.Serializer):
    highlight = StoryHighlightSerializer()


class StoryHighlightSetCoverResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StoryHighlightSetCoverResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class StoryHighlightListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Stories"],
        responses={200: StoryHighlightListResponseSerializer},
        parameters=[
            OpenApiParameter(
                name="user_id",
                description="User ID",
                required=False,  # optional since you fallback to request.user
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,  # changed to QUERY
            )
        ],
        description="Get all story highlights for the authenticated user or a specified user.",
    )
    def get(self, request):
        try:
            user_id = request.query_params.get("user_id", None)
            if user_id:
                user = get_object_or_404(User, pk=user_id)
                highlights = StoryHighlightService.get_user_highlights(user)
            else:
                highlights = StoryHighlightService.get_user_highlights(request.user)
                
            serializer = StoryHighlightSerializer(highlights, many=True, context={"request": request})
            return Response(
                {
                    "status": True,
                    "message": "Highlights retrieved.",
                    "data": {"highlights": serializer.data},
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("Error retrieving highlights")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Storie's"],
        request=StoryHighlightCreateSerializer,
        responses={201: StoryHighlightCreateResponseSerializer},
        description="Create a new story highlight with selected stories.",
    )
    def post(self, request):
        serializer = StoryHighlightCreateSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            highlight = StoryHighlightService.create_highlight(
                user=request.user,
                title=serializer.validated_data.get("title", ""),
                story_ids=serializer.validated_data["story_ids"],
            )
        except Exception as exc:
            logger.exception("Error creating highlight")
            return Response(
                {
                    "status": False,
                    "message": str(exc),
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        out_serializer = StoryHighlightSerializer(highlight, context={"request": request})
        return Response(
            {
                "status": True,
                "message": "Highlight created.",
                "data": {"highlight": out_serializer.data},
            },
            status=status.HTTP_201_CREATED,
        )


class StoryHighlightDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, id, user):
        return get_object_or_404(StoryHighlight, pk=id, user=user)

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="id",
                description="Highlight ID",
                required=True,
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
            )
        ],
        responses={200: StoryHighlightDetailResponseSerializer},
        description="Retrieve a single story highlight.",
    )
    def get(self, request, id):
        try:
            highlight = self.get_object(id, request.user)
            serializer = StoryHighlightSerializer(highlight, context={"request": request})
            return Response(
                {
                    "status": True,
                    "message": "Highlight retrieved.",
                    "data": {"highlight": serializer.data},
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("Error retrieving highlight %s", id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="id",
                description="Highlight ID",
                required=True,
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
            )
        ],
        request=StoryHighlightUpdateSerializer,
        responses={200: StoryHighlightUpdateResponseSerializer},
        description="Update a story highlight (title and/or stories).",
    )
    def put(self, request, id):
        highlight = self.get_object(id, request.user)
        serializer = StoryHighlightUpdateSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            updated = StoryHighlightService.update_highlight(
                highlight,
                title=serializer.validated_data.get("title"),
                story_ids=serializer.validated_data.get("story_ids"),
            )
        except Exception as exc:
            logger.exception("Error updating highlight %s", id)
            return Response(
                {
                    "status": False,
                    "message": str(exc),
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        out_serializer = StoryHighlightSerializer(updated, context={"request": request})
        return Response(
            {
                "status": True,
                "message": "Highlight updated.",
                "data": {"highlight": out_serializer.data},
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="id",
                description="Highlight ID",
                required=True,
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
            )
        ],
        responses={204: StoryHighlightDeleteResponseSerializer},
        description="Delete a story highlight.",
    )
    def delete(self, request, id):
        try:
            highlight = self.get_object(id, request.user)
            StoryHighlightService.delete_highlight(highlight)
            return Response(
                {
                    "status": True,
                    "message": "Highlight deleted.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        except Exception as e:
            logger.exception("Error deleting highlight %s", id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StoryHighlightAddStoriesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="id",
                description="Highlight ID",
                required=True,
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
            )
        ],
        request=StoryHighlightAddStoriesSerializer,
        responses={200: StoryHighlightAddStoriesResponseSerializer},
        description="Add stories to a highlight (does not remove existing).",
    )
    def post(self, request, id):
        highlight = get_object_or_404(StoryHighlight, pk=id, user=request.user)
        serializer = StoryHighlightAddStoriesSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            updated = StoryHighlightService.add_stories_to_highlight(
                highlight, serializer.validated_data["story_ids"]
            )
        except Exception as exc:
            logger.exception("Error adding stories to highlight %s", id)
            return Response(
                {
                    "status": False,
                    "message": str(exc),
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        out_serializer = StoryHighlightSerializer(updated, context={"request": request})
        return Response(
            {
                "status": True,
                "message": "Stories added.",
                "data": {"highlight": out_serializer.data},
            },
            status=status.HTTP_200_OK,
        )


class StoryHighlightRemoveStoriesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="id",
                description="Highlight ID",
                required=True,
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
            )
        ],
        request=StoryHighlightRemoveStoriesSerializer,
        responses={200: StoryHighlightRemoveStoriesResponseSerializer},
        description="Remove stories from a highlight.",
    )
    def post(self, request, id):
        highlight = get_object_or_404(StoryHighlight, pk=id, user=request.user)
        serializer = StoryHighlightRemoveStoriesSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            updated = StoryHighlightService.remove_stories_from_highlight(
                highlight, serializer.validated_data["story_ids"]
            )
        except Exception as exc:
            logger.exception("Error removing stories from highlight %s", id)
            return Response(
                {
                    "status": False,
                    "message": str(exc),
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        out_serializer = StoryHighlightSerializer(updated, context={"request": request})
        return Response(
            {
                "status": True,
                "message": "Stories removed.",
                "data": {"highlight": out_serializer.data},
            },
            status=status.HTTP_200_OK,
        )


class StoryHighlightSetCoverView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(
                name="id",
                description="Highlight ID",
                required=True,
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
            )
        ],
        request=StoryHighlightSetCoverSerializer,
        responses={200: StoryHighlightSetCoverResponseSerializer},
        description="Set the cover story for a highlight. The story must belong to the user and be part of the highlight.",
    )
    def post(self, request, id):
        highlight = get_object_or_404(StoryHighlight, pk=id, user=request.user)
        serializer = StoryHighlightSetCoverSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        cover_story_id = serializer.validated_data["cover_story_id"]

        try:
            updated = StoryHighlightService.set_highlight_cover(highlight, request.user, cover_story_id)
        except PermissionDenied:
            return Response(
                {
                    "status": False,
                    "message": "Permission denied.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except ObjectDoesNotExist as exc:
            return Response(
                {
                    "status": False,
                    "message": str(exc),
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            msg = exc.message if hasattr(exc, "message") else str(exc)
            return Response(
                {
                    "status": False,
                    "message": msg,
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception("Error setting cover for highlight %s", id)
            return Response(
                {
                    "status": False,
                    "message": str(exc),
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        out_serializer = StoryHighlightSerializer(updated, context={"request": request})
        return Response(
            {
                "status": True,
                "message": "Cover story set.",
                "data": {"highlight": out_serializer.data},
            },
            status=status.HTTP_200_OK,
        )