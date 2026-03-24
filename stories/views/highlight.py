# stories/views/highlight.py

from rest_framework.views import APIView, PermissionDenied
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from stories.models import StoryHighlight
from stories.services.highlight import StoryHighlightService
from stories.serializers.highlight import (
    StoryHighlightSerializer,
    StoryHighlightCreateSerializer,
    StoryHighlightSetCoverSerializer,
    StoryHighlightUpdateSerializer,
    StoryHighlightAddStoriesSerializer,
    StoryHighlightRemoveStoriesSerializer,
)


class StoryHighlightListView(APIView):
    """List and create story highlights for the authenticated user."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        responses={200: StoryHighlightSerializer(many=True)},
        description="Get all story highlights for the authenticated user.",
    )
    def get(self, request):
        highlights = StoryHighlightService.get_user_highlights(request.user)
        serializer = StoryHighlightSerializer(highlights, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Storie's"],
        request=StoryHighlightCreateSerializer,
        responses={201: StoryHighlightSerializer},
        description="Create a new story highlight with selected stories.",
    )
    def post(self, request):
        serializer = StoryHighlightCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            highlight = StoryHighlightService.create_highlight(
                user=request.user,
                title=serializer.validated_data.get("title", ""),
                story_ids=serializer.validated_data["story_ids"],
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out_serializer = StoryHighlightSerializer(highlight, context={"request": request})
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class StoryHighlightDetailView(APIView):
    """Retrieve, update, or delete a specific highlight owned by the authenticated user."""
    permission_classes = [IsAuthenticated]

    def get_object(self, id, user):
        return get_object_or_404(StoryHighlight, pk=id, user=user)

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(name="id", description="Highlight ID", required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH)
        ],
        responses={200: StoryHighlightSerializer},
        description="Retrieve a single story highlight.",
    )
    def get(self, request, id):
        highlight = self.get_object(id, request.user)
        serializer = StoryHighlightSerializer(highlight, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(name="id", description="Highlight ID", required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH)
        ],
        request=StoryHighlightUpdateSerializer,
        responses={200: StoryHighlightSerializer},
        description="Update a story highlight (title and/or stories).",
    )
    def put(self, request, id):
        highlight = self.get_object(id, request.user)
        serializer = StoryHighlightUpdateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            updated = StoryHighlightService.update_highlight(
                highlight,
                title=serializer.validated_data.get("title"),
                story_ids=serializer.validated_data.get("story_ids"),
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out_serializer = StoryHighlightSerializer(updated, context={"request": request})
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(name="id", description="Highlight ID", required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH)
        ],
        responses={204: None},
        description="Delete a story highlight.",
    )
    def delete(self, request, id):
        highlight = self.get_object(id, request.user)
        StoryHighlightService.delete_highlight(highlight)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StoryHighlightAddStoriesView(APIView):
    """Add stories to an existing highlight."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(name="id", description="Highlight ID", required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH)
        ],
        request=StoryHighlightAddStoriesSerializer,
        responses={200: StoryHighlightSerializer},
        description="Add stories to a highlight (does not remove existing).",
    )
    def post(self, request, id):
        highlight = get_object_or_404(StoryHighlight, pk=id, user=request.user)
        serializer = StoryHighlightAddStoriesSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            updated = StoryHighlightService.add_stories_to_highlight(highlight, serializer.validated_data["story_ids"])
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out_serializer = StoryHighlightSerializer(updated, context={"request": request})
        return Response(out_serializer.data, status=status.HTTP_200_OK)


class StoryHighlightRemoveStoriesView(APIView):
    """Remove stories from a highlight."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Storie's"],
        parameters=[
            OpenApiParameter(name="id", description="Highlight ID", required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH)
        ],
        request=StoryHighlightRemoveStoriesSerializer,
        responses={200: StoryHighlightSerializer},
        description="Remove stories from a highlight.",
    )
    def post(self, request, id):
        highlight = get_object_or_404(StoryHighlight, pk=id, user=request.user)
        serializer = StoryHighlightRemoveStoriesSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            updated = StoryHighlightService.remove_stories_from_highlight(highlight, serializer.validated_data["story_ids"])
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out_serializer = StoryHighlightSerializer(updated, context={"request": request})
        return Response(out_serializer.data, status=status.HTTP_200_OK)

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
        responses={200: StoryHighlightSerializer},
        description="Set the cover story for a highlight. The story must belong to the user and be part of the highlight.",
    )
    def post(self, request, id):
        highlight = get_object_or_404(StoryHighlight, pk=id, user=request.user)
        serializer = StoryHighlightSetCoverSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        cover_story_id = serializer.validated_data["cover_story_id"]

        try:
            updated = StoryHighlightService.set_highlight_cover(highlight, request.user, cover_story_id)
        except PermissionDenied:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        except ObjectDoesNotExist as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            # ValidationError may contain a list or message dict
            msg = exc.message if hasattr(exc, "message") else str(exc)
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out = StoryHighlightSerializer(updated, context={"request": request})
        return Response(out.data, status=status.HTTP_200_OK)
