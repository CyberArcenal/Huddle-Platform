# search/views/search_history.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.core.cache import cache
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from core.settings.dev import LOGGER
from global_utils.pagination import SearchPagination
from search.serializers.search_history import (
    ClearHistoryRequestSerializer,
    PopularSearchSerializer,
    SearchHistorySerializer,
    SearchStatisticsSerializer,
    RecordSearchInputSerializer,
)
from search.services.search_history import SearchHistoryService
from users.models import User

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_history(paginator, page, request):
    """
    Construct a paginated data dict that matches PaginatedSearchHistoryData.
    """
    serializer = SearchHistorySerializer(page, many=True, context={'request': request})
    data = {
        'page': paginator.page.number,
        'hasNext': paginator.page.has_next(),
        'hasPrev': paginator.page.has_previous(),
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class PaginatedSearchHistoryData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = SearchHistorySerializer(many=True)


class SearchHistoryListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedSearchHistoryData()


class SearchHistoryCreateResponseData(serializers.Serializer):
    entry = SearchHistorySerializer()


class SearchHistoryCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SearchHistoryCreateResponseData()


class SearchHistoryDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class ClearHistoryResponseData(serializers.Serializer):
    deleted = serializers.IntegerField()
    message = serializers.CharField()


class ClearHistoryResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ClearHistoryResponseData()


class DeleteEntryResponseData(serializers.Serializer):
    message = serializers.CharField()


class DeleteEntryResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = DeleteEntryResponseData(allow_null=True)


class RecentSearchesResponseData(serializers.Serializer):
    count = serializers.IntegerField()
    results = serializers.ListField(child=serializers.CharField())


class RecentSearchesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = RecentSearchesResponseData()


class PopularSearchesResponseData(serializers.Serializer):
    count = serializers.IntegerField()
    results = PopularSearchSerializer(many=True)


class PopularSearchesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PopularSearchesResponseData()


class SearchSuggestionsResponseData(serializers.Serializer):
    count = serializers.IntegerField()
    prefix = serializers.CharField()
    suggestions = serializers.ListField(child=serializers.CharField())


class SearchSuggestionsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SearchSuggestionsResponseData()


class SearchStatisticsResponseData(serializers.Serializer):
    statistics = SearchStatisticsSerializer()


class SearchStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SearchStatisticsResponseData()


class SearchTrendsResponseData(serializers.Serializer):
    count = serializers.IntegerField()
    interval = serializers.CharField()
    trends = serializers.ListField(child=serializers.DictField())


class SearchTrendsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SearchTrendsResponseData()


class ExportSearchHistoryResponseData(serializers.Serializer):
    exported_data = serializers.JSONField()


class ExportSearchHistoryResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = ExportSearchHistoryResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class SearchHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Search's History"],
        parameters=[
            OpenApiParameter(
                name="search_type",
                type=str,
                description="Filter by type (all, users, groups, posts)",
                required=False,
            ),
            OpenApiParameter(
                name="days",
                type=int,
                description="Filter by last X days",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: SearchHistoryListResponseSerializer},
        description="Retrieve the authenticated user's search history, with optional filters and pagination.",
    )
    def get(self, request):
        try:
            search_type = request.query_params.get("search_type")
            days = request.query_params.get("days")
            days = int(days) if days else None

            history = SearchHistoryService.get_user_search_history(
                user=request.user,
                search_type=search_type,
                days=days,
            )

            paginator = SearchPagination()
            page = paginator.paginate_queryset(history, request)
            paginated_data = wrap_paginated_history(paginator, page, request)

            return Response(
                {
                    "status": True,
                    "message": "Search history retrieved.",
                    "data": paginated_data,
                }
            )

        except Exception as e:
            logger.exception("SearchHistoryAPIView GET error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        tags=["Search's History"],
        request=RecordSearchInputSerializer,
        responses={201: SearchHistoryCreateResponseSerializer},
        examples=[
            OpenApiExample(
                "Record search",
                value={"query": "python", "search_type": "all", "results_count": 42},
                request_only=True,
            ),
            OpenApiExample(
                "Response",
                value={
                    "status": True,
                    "message": "Search recorded successfully",
                    "data": {
                        "entry": {
                            "id": 1,
                            "user": 1,
                            "query": "python",
                            "search_type": "all",
                            "results_count": 42,
                            "searched_at": "2025-03-07T12:34:56Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
        description="Record a new search entry.",
    )
    @transaction.atomic
    def post(self, request):
        try:
            input_serializer = RecordSearchInputSerializer(data=request.data)
            if not input_serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": input_serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            data = input_serializer.validated_data
            search_record = SearchHistoryService.record_search(
                user=request.user,
                query=data.get("query", ""),
                search_type=data.get("search_type", "all"),
                results_count=data.get("results_count", 0),
            )

            output_serializer = SearchHistorySerializer(search_record)

            cache_key = f"search_suggestions_{request.user.id}"
            cache.delete(cache_key)

            return Response(
                {
                    "status": True,
                    "message": "Search recorded successfully",
                    "data": {"entry": output_serializer.data},
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.exception("SearchHistoryAPIView POST error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        tags=["Search's History"],
        request=ClearHistoryRequestSerializer,
        responses={200: ClearHistoryResponseSerializer},
        examples=[
            OpenApiExample(
                "Clear history request",
                value={"older_than_days": 30, "search_type": "all"},
                request_only=True,
            ),
            OpenApiExample(
                "Clear history response",
                value={
                    "status": True,
                    "message": "Successfully deleted 15 search records",
                    "data": {"deleted": 15, "message": "Successfully deleted 15 search records"},
                },
                response_only=True,
            ),
        ],
        description="Clear the user's search history, optionally filtering by age or type.",
    )
    @transaction.atomic
    def delete(self, request):
        try:
            serializer = ClearHistoryRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            data = serializer.validated_data
            result = SearchHistoryService.clear_user_history(
                user=request.user,
                older_than_days=data.get("older_than_days"),
                search_type=data.get("search_type"),
            )

            # Clear all related caches
            cache_keys = [
                f"search_suggestions_{request.user.id}",
                f"search_stats_{request.user.id}",
                f"search_popular_{request.user.id}",
            ]
            for key in cache_keys:
                cache.delete(key)

            return Response(
                {
                    "status": True,
                    "message": f'Successfully deleted {result["deleted"]} search records',
                    "data": {"deleted": result["deleted"], "message": result.get("message", "")},
                }
            )

        except Exception as e:
            logger.exception("SearchHistoryAPIView DELETE error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class DeleteSearchEntryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Search's History"],
        responses={
            200: DeleteEntryResponseSerializer,
            404: DeleteEntryResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Success",
                value={
                    "status": True,
                    "message": "Search entry deleted successfully",
                    "data": {"message": "Search entry deleted successfully"},
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Not found",
                value={
                    "status": False,
                    "message": "Search entry not found or you do not have permission",
                    "data": None,
                },
                response_only=True,
                status_codes=["404"],
            ),
        ],
        description="Delete a specific search history entry by its ID.",
    )
    @transaction.atomic
    def delete(self, request, entry_id):
        try:
            success = SearchHistoryService.delete_search_entry(
                entry_id=entry_id, user=request.user
            )

            if success:
                return Response(
                    {
                        "status": True,
                        "message": "Search entry deleted successfully",
                        "data": {"message": "Search entry deleted successfully"},
                    }
                )
            else:
                return Response(
                    {
                        "status": False,
                        "message": "Search entry not found or you do not have permission",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        except Exception as e:
            logger.exception("DeleteSearchEntryAPIView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class RecentSearchesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(cache_page(60 * 5))
    @method_decorator(vary_on_cookie)
    @extend_schema(
        tags=["Search's History"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of results (default 10)",
                required=False,
            ),
            OpenApiParameter(
                name="unique",
                type=bool,
                description="Return unique queries only",
                required=False,
            ),
        ],
        responses={200: RecentSearchesResponseSerializer},
        examples=[
            OpenApiExample(
                "Response",
                value={
                    "status": True,
                    "message": "Recent searches retrieved.",
                    "data": {
                        "count": 3,
                        "results": ["python", "django", "react"],
                    },
                },
                response_only=True,
            )
        ],
        description="Get a list of the user's recent search queries.",
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 10))
            unique = request.query_params.get("unique", "true").lower() == "true"

            recent_searches = SearchHistoryService.get_recent_searches(
                user=request.user, limit=min(limit, 50), unique_queries=unique
            )

            return Response(
                {
                    "status": True,
                    "message": "Recent searches retrieved.",
                    "data": {
                        "count": len(recent_searches),
                        "results": recent_searches,
                    },
                }
            )

        except Exception as e:
            logger.exception("RecentSearchesAPIView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class PopularSearchesAPIView(APIView):
    @method_decorator(cache_page(60 * 30))
    @extend_schema(
        tags=["Search's History"],
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                description="Time period in days (default 7)",
                required=False,
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of results (default 10)",
                required=False,
            ),
            OpenApiParameter(
                name="search_type",
                type=str,
                description="Filter by search type",
                required=False,
            ),
            OpenApiParameter(
                name="user_only",
                type=bool,
                description="Show only user's popular searches (auth required)",
                required=False,
            ),
        ],
        responses={200: PopularSearchesResponseSerializer},
        examples=[
            OpenApiExample(
                "Response",
                value={
                    "status": True,
                    "message": "Popular searches retrieved.",
                    "data": {
                        "count": 3,
                        "results": [
                            {"query": "django", "count": 150},
                            {"query": "python", "count": 120},
                            {"query": "react", "count": 90},
                        ],
                    },
                },
                response_only=True,
            )
        ],
        description="Get globally popular searches or, if user_only=true, popular searches for the authenticated user.",
    )
    def get(self, request):
        try:
            days = int(request.query_params.get("days", 7))
            limit = int(request.query_params.get("limit", 10))
            search_type = request.query_params.get("search_type")
            user_only = request.query_params.get("user_only", "false").lower() == "true"

            if user_only and request.user.is_authenticated:
                popular_searches = SearchHistoryService.get_user_popular_searches(
                    user=request.user, days=min(days, 365), limit=min(limit, 50)
                )
            else:
                popular_searches = SearchHistoryService.get_popular_searches(
                    days=min(days, 365), limit=min(limit, 50), search_type=search_type
                )

            serializer = PopularSearchSerializer(popular_searches, many=True)

            return Response(
                {
                    "status": True,
                    "message": "Popular searches retrieved.",
                    "data": {
                        "count": len(popular_searches),
                        "results": serializer.data,
                    },
                }
            )

        except Exception as e:
            logger.exception("PopularSearchesAPIView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class SearchSuggestionsAPIView(APIView):
    @extend_schema(
        tags=["Search's History"],
        parameters=[
            OpenApiParameter(
                name="prefix",
                type=str,
                description="Search prefix (required)",
                required=True,
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of suggestions (default 10)",
                required=False,
            ),
            OpenApiParameter(
                name="include_anonymous",
                type=bool,
                description="Include anonymous searches",
                required=False,
            ),
        ],
        responses={200: SearchSuggestionsResponseSerializer},
        examples=[
            OpenApiExample(
                "Response",
                value={
                    "status": True,
                    "message": "Suggestions retrieved.",
                    "data": {
                        "count": 3,
                        "prefix": "py",
                        "suggestions": ["python", "pytest", "pygame"],
                    },
                },
                response_only=True,
            )
        ],
        description="Get autocomplete suggestions based on a prefix.",
    )
    def get(self, request):
        try:
            prefix = request.query_params.get("prefix", "").strip()
            limit = int(request.query_params.get("limit", 10))
            include_anonymous = (
                request.query_params.get("include_anonymous", "false").lower() == "true"
            )

            if not prefix:
                return Response(
                    {
                        "status": False,
                        "message": "Prefix parameter is required",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if request.user.is_authenticated:
                cache_key = f"search_suggestions_{request.user.id}_{prefix}_{limit}"
                suggestions = cache.get(cache_key)

                if not suggestions:
                    suggestions = SearchHistoryService.get_suggestions(
                        user=request.user,
                        prefix=prefix,
                        limit=min(limit, 20),
                        include_anonymous=include_anonymous,
                    )
                    cache.set(cache_key, suggestions, 60 * 10)
            else:
                suggestions = SearchHistoryService.get_suggestions(
                    user=None,
                    prefix=prefix,
                    limit=min(limit, 20),
                    include_anonymous=True,
                )

            return Response(
                {
                    "status": True,
                    "message": "Suggestions retrieved.",
                    "data": {
                        "count": len(suggestions),
                        "prefix": prefix,
                        "suggestions": suggestions,
                    },
                }
            )

        except Exception as e:
            logger.exception("SearchSuggestionsAPIView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class SearchStatisticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(cache_page(60 * 10))
    @method_decorator(vary_on_cookie)
    @extend_schema(
        tags=["Search's History"],
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                description="Time period in days (default 30)",
                required=False,
            ),
        ],
        responses={200: SearchStatisticsResponseSerializer},
        examples=[
            OpenApiExample(
                "Response",
                value={
                    "status": True,
                    "message": "Search statistics retrieved.",
                    "data": {
                        "statistics": {
                            "total_searches": 250,
                            "unique_queries": 45,
                            "avg_results_per_search": 12.3,
                            "top_search_types": {
                                "all": 150,
                                "users": 50,
                                "groups": 30,
                                "posts": 20,
                            },
                        }
                    },
                },
                response_only=True,
            )
        ],
        description="Get search statistics for the authenticated user.",
    )
    def get(self, request):
        try:
            days = int(request.query_params.get("days", 30))

            statistics = SearchHistoryService.get_search_statistics(
                user=request.user, days=min(days, 365)
            )

            return Response(
                {
                    "status": True,
                    "message": "Search statistics retrieved.",
                    "data": {"statistics": statistics},
                }
            )

        except Exception as e:
            logger.exception("SearchStatisticsAPIView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class SearchTrendsAPIView(APIView):
    @method_decorator(cache_page(60 * 60))
    @extend_schema(
        tags=["Search's History"],
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                description="Time period in days (default 7)",
                required=False,
            ),
            OpenApiParameter(
                name="interval",
                type=str,
                description="Grouping interval (day/hour)",
                required=False,
            ),
        ],
        responses={200: SearchTrendsResponseSerializer},
        examples=[
            OpenApiExample(
                "Response",
                value={
                    "status": True,
                    "message": "Search trends retrieved.",
                    "data": {
                        "count": 7,
                        "interval": "day",
                        "trends": [
                            {"date": "2025-03-01", "count": 42},
                            {"date": "2025-03-02", "count": 38},
                        ],
                    },
                },
                response_only=True,
            )
        ],
        description="Get search volume trends over time.",
    )
    def get(self, request):
        try:
            days = int(request.query_params.get("days", 7))
            interval = request.query_params.get("interval", "day")

            if interval not in ["day", "hour"]:
                return Response(
                    {
                        "status": False,
                        "message": 'Interval must be either "day" or "hour"',
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            trends = SearchHistoryService.get_search_trends(
                days=min(days, 90), interval=interval
            )

            return Response(
                {
                    "status": True,
                    "message": "Search trends retrieved.",
                    "data": {
                        "count": len(trends),
                        "interval": interval,
                        "trends": trends,
                    },
                }
            )

        except Exception as e:
            logger.exception("SearchTrendsAPIView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class ExportSearchHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Search's History"],
        parameters=[
            OpenApiParameter(
                name="format",
                type=str,
                description="Export format (json)",
                required=False,
            ),
            OpenApiParameter(
                name="include_metadata",
                type=bool,
                description="Include metadata",
                required=False,
            ),
        ],
        responses={200: ExportSearchHistoryResponseSerializer},
        examples=[
            OpenApiExample(
                "Response (file download)",
                value={
                    "status": True,
                    "message": "Search history exported.",
                    "data": {
                        "exported_data": {
                            "searches": [
                                {"query": "django rest framework", "timestamp": "2025-03-08T10:00:00Z"},
                                {"query": "python uuid", "timestamp": "2025-03-08T10:05:00Z"}
                            ],
                            "metadata": {"total": 2}
                        }
                    },
                },
                response_only=True,
            )
        ],
        description="Export the user's search history as a JSON file.",
    )
    def get(self, request):
        try:
            export_format = request.query_params.get("format", "json")
            include_metadata = (
                request.query_params.get("include_metadata", "true").lower() == "true"
            )

            if export_format != "json":
                return Response(
                    {
                        "status": False,
                        "message": "Only JSON export format is currently supported",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            export_data = SearchHistoryService.export_user_search_history(
                user=request.user,
                format=export_format,
                include_metadata=include_metadata,
            )

            response = Response(
                {
                    "status": True,
                    "message": "Search history exported.",
                    "data": {"exported_data": export_data},
                }
            )
            response["Content-Disposition"] = (
                f'attachment; filename="search_history_{request.user.username}.json"'
            )
            response["Content-Type"] = "application/json"

            return response

        except Exception as e:
            logger.exception("ExportSearchHistoryAPIView error")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )