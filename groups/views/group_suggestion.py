# groups/views/group_suggestion.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from global_utils.pagination import GroupsPagination
from groups.services.group_suggestion import GroupSuggestionService
from groups.serializers.suggestion import GroupSuggestionItemSerializer
from rest_framework import serializers


class PaginatedGroupSuggestionSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = GroupSuggestionItemSerializer(many=True)


class GroupSuggestionView(APIView):
    """View for getting ranked group recommendations."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Group Suggestion"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of suggestions per page (default 20)",
                required=False,
            ),
            OpenApiParameter(
                name="offset",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Offset for pagination (default 0)",
                required=False,
            ),
        ],
        responses={200: PaginatedGroupSuggestionSerializer},
        description="Get personalized group suggestions for the authenticated user.",
    )
    def get(self, request):
        # Get pagination parameters
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))

        # Get ranked recommendations from the service
        recommendations = GroupSuggestionService.get_ranked_recommendations(
            user=request.user,
            limit=limit,
            offset=offset,
        )

        # Prepare paginated response
        # Since the service already paginates, we just return the list directly.
        # But we need to mimic the pagination structure. We can use the paginator class.
        paginator = GroupsPagination()
        # However, the service returns a list of dicts, not a queryset.
        # We'll manually create a paginated response using the paginator's get_paginated_response method.
        # But that method expects a paginated queryset. We'll instead use a custom paginator.
        # Simpler: manually paginate using page/offset and return a response that matches the schema.
        # For simplicity, we'll just use the paginator to get the page count, but we already have the list.
        # We'll just return a dict with count and results.

        # Compute total count (if we want to include it, we'd need to know total matches from the service)
        # For now, we'll just return the list and set count as the length of the list.
        # This is acceptable for a simple endpoint.
        # But to match the paginator, we'll use a custom paginator-like response.

        # Let's use the paginator's get_paginated_response but with our list.
        # We need to mimic the paginator's structure. We'll create a custom response.
        # Alternatively, we can just return the list and let the frontend handle pagination.
        # But the spec expects pagination.

        # Since we have limit and offset, we can return a response with metadata.
        # For consistency with other views, we'll create a paginated response manually.

        # We'll assume the service returns the exact slice requested, and we don't know total count.
        # For simplicity, we'll just set count to len(recommendations) and page based on offset/limit.
        page = (offset // limit) + 1 if limit else 1
        has_next = len(recommendations) == limit  # if we got exactly limit, maybe more
        has_prev = offset > 0

        # Build next/prev URLs (optional)
        base_url = request.build_absolute_uri(request.path)
        next_url = f"{base_url}?limit={limit}&offset={offset+limit}" if has_next else None
        prev_url = f"{base_url}?limit={limit}&offset={max(0, offset-limit)}" if has_prev else None

        response_data = {
            "count": len(recommendations),
            "page": page,
            "hasNext": has_next,
            "hasPrev": has_prev,
            "next": next_url,
            "previous": prev_url,
            "results": recommendations,
        }
        # Serialize the results
        serializer = GroupSuggestionItemSerializer(recommendations, many=True, context={"request": request})
        response_data["results"] = serializer.data

        return Response(response_data)