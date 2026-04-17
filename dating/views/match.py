# dating/views/match.py
import logging
from rest_framework.views import APIView, PermissionDenied
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from dating.models.dating_preference import DatingPreference
from dating.serializers.match import MatchCreateSerializer, MatchDetailSerializer, MatchMinimalSerializer, MatchUnmatchSerializer
from global_utils.pagination import UsersPagination
from dating.services.matching import MatchingService
from users.serializers.matching import (
    UserMatchScoreSerializer,
    FriendSuggestionsSerializer,
    UserMutualCountSerializer,
)
from django.db import transaction
from django.db import models
from dating.models import Match

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class PaginatedMatchScoresData(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = UserMatchScoreSerializer(many=True)


class MatchScoresResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedMatchScoresData()


class PaginatedMatchData(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = MatchMinimalSerializer(many=True)


class ActiveMatchesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedMatchData()


class MatchDetailResponseData(serializers.Serializer):
    match = MatchDetailSerializer()


class MatchDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MatchDetailResponseData()


class MatchCreateResponseData(serializers.Serializer):
    match = MatchDetailSerializer()


class MatchCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MatchCreateResponseData()


class MatchUnmatchResponseData(serializers.Serializer):
    success = serializers.BooleanField()
    unmatched_id = serializers.IntegerField()


class MatchUnmatchResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MatchUnmatchResponseData()


# ----------------------------------------------------------------------
# Helper to build paginated response for match scores
# ----------------------------------------------------------------------
def build_paginated_match_scores(request, matches, limit, offset, total):
    """Return a data dict matching PaginatedMatchScoresData."""
    page = (offset // limit) + 1 if limit else 1
    has_next = offset + limit < total
    has_prev = offset > 0

    base_url = request.build_absolute_uri(request.path)
    next_url = f"{base_url}?limit={limit}&offset={offset+limit}" if has_next else None
    prev_url = f"{base_url}?limit={limit}&offset={max(0, offset-limit)}" if has_prev else None

    # Convert matches to list of dicts with user and score
    results_data = [{'user': m['user'], 'score': m['score']} for m in matches]
    serializer = UserMatchScoreSerializer(results_data, many=True, context={'request': request})

    return {
        'count': total,
        'page': page,
        'hasNext': has_next,
        'hasPrev': has_prev,
        'next': next_url,
        'previous': prev_url,
        'results': serializer.data,
    }


def build_paginated_matches(request, queryset, limit, offset):
    """Return a data dict matching PaginatedMatchData."""
    total = queryset.count()
    matches = queryset[offset:offset + limit]

    page = (offset // limit) + 1 if limit else 1
    has_next = offset + limit < total
    has_prev = offset > 0

    base_url = request.build_absolute_uri(request.path)
    next_url = f"{base_url}?limit={limit}&offset={offset+limit}" if has_next else None
    prev_url = f"{base_url}?limit={limit}&offset={max(0, offset-limit)}" if has_prev else None

    results_data = MatchMinimalSerializer(matches, many=True, context={'request': request}).data
    return {
        'count': total,
        'page': page,
        'hasNext': has_next,
        'hasPrev': has_prev,
        'next': next_url,
        'previous': prev_url,
        'results': results_data,
    }


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class UserMatchScoresView(APIView):
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
        responses={200: MatchScoresResponseSerializer},
        description="Get a paginated list of potential matches with their scores.",
    )
    def get(self, request):
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

        try:
            matches, total = MatchingService.get_matches_paginated(
                user=request.user,
                limit=limit,
                offset=offset,
                filters=filters
            )
            data = build_paginated_match_scores(request, matches, limit, offset, total)
            return Response(
                {
                    "status": True,
                    "message": "Match scores retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error fetching match scores")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ActiveMatchesListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Matches"],
        parameters=[
            OpenApiParameter(
                name="limit", type=int, description="Number of results per page", required=False
            ),
            OpenApiParameter(
                name="offset", type=int, description="Offset for pagination", required=False
            ),
        ],
        responses={200: ActiveMatchesResponseSerializer},
        description="List all active matches for the current user, with pagination.",
    )
    def get(self, request):
        user = request.user
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))

        queryset = Match.objects.filter(
            is_active=True
        ).filter(
            models.Q(user1=user) | models.Q(user2=user)
        ).order_by('-created_at')

        data = build_paginated_matches(request, queryset, limit, offset)
        return Response(
            {
                "status": True,
                "message": "Active matches retrieved.",
                "data": data,
            }
        )


class MatchDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Matches"],
        responses={200: MatchDetailResponseSerializer},
        description="Retrieve details of a specific match.",
    )
    def get(self, request, pk):
        try:
            match = Match.objects.get(pk=pk)
        except Match.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Match not found.",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user not in (match.user1, match.user2):
            raise PermissionDenied("You are not part of this match.")

        serializer = MatchDetailSerializer(match, context={'request': request})
        return Response(
            {
                "status": True,
                "message": "Match details retrieved.",
                "data": {"match": serializer.data},
            }
        )


class MatchCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Matches"],
        request=MatchCreateSerializer,
        responses={201: MatchCreateResponseSerializer},
        description="Create a new match.",
    )
    
    def post(self, request):
        try:
            serializer = MatchCreateSerializer(data=request.data, context={'request': request})
            response = {
                        "status": False,
                        "message": "Something went wrong.",
                        "data": None,
                    }
            with transaction.atomic():
                serializer.is_valid(raise_exception=True)
                match = serializer.save()
                output_serializer = MatchDetailSerializer(match, context={'request': request})
                response["data"] = {"match": output_serializer.data}
                response["status"] = True
                response["message"] = "Match created."
                return Response(
                    response,
                    status=status.HTTP_201_CREATED,
                )
            
            return Response(response, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            if "Match already exists" in str(e):
                return Response(
                {
                    "status": True,
                    "message": "Match already exists. Reactivated existing match.",
                    "data": None,
                },
                status=status.HTTP_201_CREATED,
            )
                
            logger.exception(f"Error creating match: {e}")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class MatchUnmatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Matches"],
        request=MatchUnmatchSerializer,
        responses={200: MatchUnmatchResponseSerializer},
        description="Deactivate a match (unmatch).",
    )
    def post(self, request):
        serializer = MatchUnmatchSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            {
                "status": True,
                "message": "Match unmatch.",
                "data": result,
            },
            status=status.HTTP_200_OK,
        )