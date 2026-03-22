from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from django.core.exceptions import ObjectDoesNotExist
from typing import Type, List, Any

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

    def get(self, request):
        """GET: Return available options + user's selected ones."""
        available = self.get_available_options()
        user_selected = self.get_user_selected(request.user)

        available_serializer = self.serializer_class(available, many=True)
        selected_serializer = self.serializer_class(user_selected, many=True)

        return Response({
            'available': available_serializer.data,
            'selected': selected_serializer.data
        })

    def put(self, request):
        """PUT: Replace the user's selected options with the provided IDs."""
        # Input: list of IDs
        ids = request.data.get('ids', [])
        if not isinstance(ids, list):
            return Response(
                {'error': 'ids must be a list of integers'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate that all IDs exist
        existing_ids = set(self.model_class.objects.filter(id__in=ids).values_list('id', flat=True))
        missing_ids = set(ids) - existing_ids
        if missing_ids:
            return Response(
                {'error': f'Invalid IDs: {list(missing_ids)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Set the new set
        relation = getattr(request.user, self.relation_name)
        relation.set(ids)

        return Response({
            'message': f'{self.relation_name} updated successfully',
            'selected': self.serializer_class(relation.all(), many=True).data
        })