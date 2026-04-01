from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from django.core.exceptions import ObjectDoesNotExist
from typing import Type, List, Any
from rest_framework import serializers
import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------
class BaseUserPreferenceGetResponseData(serializers.Serializer):
    available = serializers.ListField(child=serializers.DictField())
    selected = serializers.ListField(child=serializers.DictField())


class BaseUserPreferenceGetResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = BaseUserPreferenceGetResponseData()


class BaseUserPreferencePutResponseData(serializers.Serializer):
    message = serializers.CharField()
    selected = serializers.ListField(child=serializers.DictField())


class BaseUserPreferencePutResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = BaseUserPreferencePutResponseData()


# ----------------------------------------------------------------------
# Base view
# ----------------------------------------------------------------------
class BaseUserPreferenceView(APIView):
    """
    Base view for managing user M2M preferences (hobbies, interests, etc.)
    Subclasses must define:
        - model_class: the model class (e.g., Hobby)
        - serializer_class: serializer for the model (list/read)
        - relation_name: name of the reverse relation on User (e.g., 'hobbies')
    """
    permission_classes = [IsAuthenticated]
    model_class = None
    serializer_class = None
    relation_name = None

    def get_available_options(self) -> List[Any]:
        """Return all available options."""
        return self.model_class.objects.all()

    def get_user_selected(self, user) -> List[Any]:
        """Return the user's selected options for this relation."""
        return getattr(user, self.relation_name).all()

    @extend_schema(
        tags=["User Preferences"],
        responses={200: BaseUserPreferenceGetResponseSerializer},
        description="Get available options and the user's selected ones for this preference.",
    )
    def get(self, request):
        try:
            available = self.get_available_options()
            user_selected = self.get_user_selected(request.user)

            available_serializer = self.serializer_class(available, many=True)
            selected_serializer = self.serializer_class(user_selected, many=True)

            return Response(
                {
                    "status": True,
                    "message": f"{self.relation_name} retrieved.",
                    "data": {
                        "available": available_serializer.data,
                        "selected": selected_serializer.data,
                    },
                }
            )
        except Exception as e:
            logger.exception(f"Error retrieving {self.relation_name}")
            return Response(
                {
                    "status": False,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ----- Input serializer for PUT -----
    class PutInputSerializer(serializers.Serializer):
        ids = serializers.ListField(
            child=serializers.IntegerField(),
            help_text="List of option IDs to set as the user's selection."
        )

    @extend_schema(
        tags=["User Preferences"],
        request=PutInputSerializer,
        responses={200: BaseUserPreferencePutResponseSerializer},
        description="Replace the user's selected options with the provided IDs.",
    )
    def put(self, request):
        # Validate input using the nested serializer
        input_serializer = self.PutInputSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": input_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ids = input_serializer.validated_data['ids']
        # Validate that all IDs exist
        existing_ids = set(self.model_class.objects.filter(id__in=ids).values_list('id', flat=True))
        missing_ids = set(ids) - existing_ids
        if missing_ids:
            return Response(
                {
                    "status": False,
                    "message": f"Invalid IDs: {list(missing_ids)}",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Set the new set
        relation = getattr(request.user, self.relation_name)
        relation.set(ids)

        # Return updated selection
        selected_serializer = self.serializer_class(relation.all(), many=True)
        return Response(
            {
                "status": True,
                "message": f"{self.relation_name} updated successfully.",
                "data": {
                    "message": f"{self.relation_name} updated successfully",
                    "selected": selected_serializer.data,
                },
            }
        )