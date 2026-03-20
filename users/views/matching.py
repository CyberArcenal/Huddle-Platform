from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from global_utils.pagination import UsersPagination
from users.services.matching import MatchingService
from users.serializers.matching import (
    UserMatchScoreSerializer,
    FriendSuggestionsSerializer,
    UserMutualCountSerializer,
)
from rest_framework import serializers


# ----- Paginated response for match scores -----
class PaginatedMatchScoresSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserMatchScoreSerializer(many=True)


class UserMatchScoresView(APIView):
    """Return a paginated list of users with match scores, sorted descending."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Matching"],
        
        parameters=[
            OpenApiParameter(
                name="limit", type=int, description="Number of results per page", required=False
            ),
            OpenApiParameter(
                name="offset", type=int, description="Offset for pagination", required=False
            ),
            OpenApiParameter(
                name="max_distance_km", type=float, description="Maximum distance in km", required=False
            ),
            OpenApiParameter(
                name="min_age", type=int, description="Minimum age", required=False
            ),
            OpenApiParameter(
                name="max_age", type=int, description="Maximum age", required=False
            ),
        ],
        responses={200: PaginatedMatchScoresSerializer},
        description="Get a paginated list of potential matches with their scores.",
    )
    def get(self, request):
        # Build filters from query params
        filters = {}
        max_distance = request.query_params.get('max_distance_km')
        min_age = request.query_params.get('min_age')
        max_age = request.query_params.get('max_age')
        if max_distance is not None:
            filters['max_distance_km'] = float(max_distance)
        if min_age is not None:
            filters['min_age'] = int(min_age)
        if max_age is not None:
            filters['max_age'] = int(max_age)

        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))

        matches = MatchingService.get_matches(
            user=request.user,
            limit=limit,
            offset=offset,
            filters=filters
        )

        # Build paginated response manually
        paginator = UsersPagination()
        # We'll use the paginator's structure but we already have the slice.
        # For simplicity, we'll create a dict that matches the paginated serializer.
        page = (offset // limit) + 1 if limit else 1
        has_next = len(matches) == limit  # if we got exactly limit, there might be more
        has_prev = offset > 0

        base_url = request.build_absolute_uri(request.path)
        next_url = f"{base_url}?limit={limit}&offset={offset+limit}" if has_next else None
        prev_url = f"{base_url}?limit={limit}&offset={max(0, offset-limit)}" if has_prev else None

        # Convert matches to a list of dicts with user and score
        results_data = [{'user': m['user'], 'score': m['score']} for m in matches]

        response_data = {
            'count': len(results_data),
            'page': page,
            'hasNext': has_next,
            'hasPrev': has_prev,
            'next': next_url,
            'previous': prev_url,
            'results': results_data,
        }
        serializer = UserMatchScoreSerializer(results_data, many=True, context={'request': request})
        response_data['results'] = serializer.data

        return Response(response_data)


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
        responses={200: FriendSuggestionsSerializer},
        description="Get friend suggestions: users with mutual connections and best matches.",
    )
    def get(self, request):
        # Build match filters
        match_filters = {}
        max_distance = request.query_params.get('max_distance_km')
        min_age = request.query_params.get('min_age')
        max_age = request.query_params.get('max_age')
        if max_distance:
            match_filters['max_distance_km'] = float(max_distance)
        if min_age:
            match_filters['min_age'] = int(min_age)
        if max_age:
            match_filters['max_age'] = int(max_age)

        limit_social = int(request.query_params.get('limit_social', 10))
        limit_matches = int(request.query_params.get('limit_matches', 10))
        offset_social = int(request.query_params.get('offset_social', 0))
        offset_matches = int(request.query_params.get('offset_matches', 0))

        suggestions = MatchingService.get_friend_suggestions(
            user=request.user,
            limit_social=limit_social,
            limit_matches=limit_matches,
            offset_social=offset_social,
            offset_matches=offset_matches,
            match_filters=match_filters
        )

        # Serialize the results
        social_serializer = UserMutualCountSerializer(
            suggestions['suggested_by_friends'], many=True, context={'request': request}
        )
        matches_serializer = UserMatchScoreSerializer(
            suggestions['best_matches'], many=True, context={'request': request}
        )

        return Response({
            'suggested_by_friends': social_serializer.data,
            'best_matches': matches_serializer.data,
        })