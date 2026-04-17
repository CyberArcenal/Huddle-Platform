from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, serializers
from drf_spectacular.utils import extend_schema, OpenApiParameter
from dating.services.matching import MatchingService
from users.serializers.matching import (
    UserMatchScoreSerializer,
    FriendSuggestionsSerializer,
    UserMutualCountSerializer,
)

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class FriendSuggestionsResponseData(serializers.Serializer):
    suggested_by_friends = UserMutualCountSerializer(many=True)
    best_matches = UserMatchScoreSerializer(many=True)


class FriendSuggestionsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = FriendSuggestionsResponseData()


# ----------------------------------------------------------------------
# View
# ----------------------------------------------------------------------

class UserFriendSuggestionsView(APIView):
    """Return combined friend suggestions (social + match-based)."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Matching"],
        parameters=[
            OpenApiParameter(
                name="limit_social", type=int, description="Number of social suggestions", required=False
            ),
            OpenApiParameter(
                name="limit_matches", type=int, description="Number of match-based suggestions", required=False
            ),
            OpenApiParameter(
                name="offset_social", type=int, description="Offset for social suggestions", required=False
            ),
            OpenApiParameter(
                name="offset_matches", type=int, description="Offset for match-based suggestions", required=False
            ),
            OpenApiParameter(
                name="max_distance_km", type=float, description="Max distance for matches", required=False
            ),
            OpenApiParameter(
                name="min_age", type=int, description="Min age for matches", required=False
            ),
            OpenApiParameter(
                name="max_age", type=int, description="Max age for matches", required=False
            ),
        ],
        responses={200: FriendSuggestionsResponseSerializer},
        description="Get friend suggestions: users with mutual connections and best matches.",
    )
    def get(self, request):
        try:
            # Extract filtering parameters
            max_distance = request.query_params.get('max_distance_km')
            min_age = request.query_params.get('min_age')
            max_age = request.query_params.get('max_age')

            limit_social = int(request.query_params.get('limit_social', 10))
            limit_matches = int(request.query_params.get('limit_matches', 10))
            offset_social = int(request.query_params.get('offset_social', 0))
            offset_matches = int(request.query_params.get('offset_matches', 0))

            # Call the service with explicit parameters (not a dict)
            suggestions = MatchingService.get_friend_suggestions(
                user=request.user,
                limit_social=limit_social,
                limit_matches=limit_matches,
                offset_social=offset_social,
                offset_matches=offset_matches,
                max_distance_km=float(max_distance) if max_distance else None,
                min_age=int(min_age) if min_age else None,
                max_age=int(max_age) if max_age else None,
            )

            social_serializer = UserMutualCountSerializer(
                suggestions['suggested_by_friends'], many=True, context={'request': request}
            )
            matches_serializer = UserMatchScoreSerializer(
                suggestions['best_matches'], many=True, context={'request': request}
            )

            return Response(
                {
                    "status": True,
                    "message": "Friend suggestions retrieved.",
                    "data": {
                        "suggested_by_friends": social_serializer.data,
                        "best_matches": matches_serializer.data,
                    },
                }
            )
        except Exception as e:
            logger.exception("UserFriendSuggestionsView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=500,
            )