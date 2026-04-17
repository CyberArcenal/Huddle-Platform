# dating/views/dating_preference.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from dating.models.dating_preference import DatingPreference
from dating.serializers.dating_preference import (
    DatingPreferenceDetailSerializer,
    DatingPreferenceCreateUpdateSerializer,
    DatingPreferenceCompatibilitySerializer,
)
from dating.services.dating_preference import DatingPreferenceService

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class DatingPreferenceResponseData(serializers.Serializer):
    preferences = DatingPreferenceDetailSerializer()


class DatingPreferenceResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = DatingPreferenceResponseData()


class DatingPreferenceCompatibilityResponseData(serializers.Serializer):
    compatibility = DatingPreferenceCompatibilitySerializer()


class DatingPreferenceCompatibilityResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = DatingPreferenceCompatibilityResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class DatingPreferenceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Dating Preferences"],
        responses={200: DatingPreferenceResponseSerializer},
        description="Retrieve the dating preferences of the authenticated user.",
    )
    def get(self, request):
        preferences = DatingPreferenceService.get_preferences(request.user)
        if not preferences:
            preferences = DatingPreferenceService.create_default_preferences(request.user)

        serializer = DatingPreferenceDetailSerializer(preferences, context={'request': request})
        return Response(
            {
                "status": True,
                "message": "Preferences retrieved.",
                "data": {"preferences": serializer.data},
            }
        )

    @extend_schema(
        tags=["Dating Preferences"],
        request=DatingPreferenceCreateUpdateSerializer,
        responses={200: DatingPreferenceResponseSerializer},
        description="Update dating preferences for the authenticated user (full update).",
    )
    def put(self, request):
        serializer = DatingPreferenceCreateUpdateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        preferences = serializer.save()
        output_serializer = DatingPreferenceDetailSerializer(preferences, context={'request': request})
        return Response(
            {
                "status": True,
                "message": "Preferences updated.",
                "data": {"preferences": output_serializer.data},
            }
        )

    @extend_schema(
        tags=["Dating Preferences"],
        request=DatingPreferenceCreateUpdateSerializer,
        responses={200: DatingPreferenceResponseSerializer},
        description="Partially update dating preferences for the authenticated user.",
    )
    def patch(self, request):
        instance = DatingPreferenceService.get_preferences(request.user)
        serializer = DatingPreferenceCreateUpdateSerializer(
            instance=instance,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        preferences = serializer.save()
        output_serializer = DatingPreferenceDetailSerializer(preferences, context={'request': request})
        return Response(
            {
                "status": True,
                "message": "Preferences partially updated.",
                "data": {"preferences": output_serializer.data},
            }
        )


class DatingPreferenceCompatibilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Dating Preferences"],
        request=DatingPreferenceCompatibilitySerializer,
        responses={200: DatingPreferenceCompatibilityResponseSerializer},
        description="Check compatibility with another user based on dating preferences.",
        examples=[
            OpenApiExample(
                "Example request",
                value={"user2": 123},
                request_only=True,
            ),
            OpenApiExample(
                "Example response",
                value={
                    "status": True,
                    "message": "Compatibility checked.",
                    "data": {
                        "compatibility": {
                            "user1_id": 1,
                            "user2_id": 123,
                            "compatible": True,
                        }
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = DatingPreferenceCompatibilitySerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            {
                "status": True,
                "message": "Compatibility checked.",
                "data": {"compatibility": result},
            },
            status=status.HTTP_200_OK,
        )