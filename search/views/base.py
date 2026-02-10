# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.core.cache import cache
from search.serializers.base import (
    ClearHistoryRequestSerializer,
    PopularSearchSerializer,
    SearchHistorySerializer,
    SearchStatisticsSerializer,
)
from search.services.search_history import SearchHistoryService
from users.models import User


class SearchHistoryAPIView(APIView):
    """API View for managing search history"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get user's search history
        Query Parameters:
        - limit: Number of results (default: 50)
        - offset: Pagination offset (default: 0)
        - search_type: Filter by type (all, users, groups, posts)
        - days: Filter by last X days
        """
        try:
            limit = int(request.query_params.get("limit", 50))
            offset = int(request.query_params.get("offset", 0))
            search_type = request.query_params.get("search_type")
            days = request.query_params.get("days")
            days = int(days) if days else None

            # Get search history
            history = SearchHistoryService.get_user_search_history(
                user=request.user,
                limit=min(limit, 100),  # Cap at 100 for safety
                offset=offset,
                search_type=search_type,
                days=days,
            )

            serializer = SearchHistorySerializer(history, many=True)

            # Get total count for pagination
            total_count = (
                SearchHistoryService.get_user_search_history(
                    user=request.user,
                    limit=None,
                    offset=0,
                    search_type=search_type,
                    days=days,
                ).count()
                if history
                else 0
            )

            return Response(
                {
                    "success": True,
                    "count": len(history),
                    "total": total_count,
                    "next": (
                        f"?limit={limit}&offset={offset+limit}"
                        if offset + limit < total_count
                        else None
                    ),
                    "previous": (
                        f"?limit={limit}&offset={max(0, offset-limit)}"
                        if offset > 0
                        else None
                    ),
                    "results": serializer.data,
                }
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )

    def post(self, request):
        """
        Record a new search
        Required Fields: query
        Optional Fields: search_type, results_count
        """
        try:
            # Extract data from request
            query = request.data.get("query", "")
            search_type = request.data.get("search_type", "all")
            results_count = request.data.get("results_count", 0)

            # Record search using service
            search_record = SearchHistoryService.record_search(
                user=request.user,
                query=query,
                search_type=search_type,
                results_count=results_count,
            )

            serializer = SearchHistorySerializer(search_record)

            # Clear cache for suggestions if exists
            cache_key = f"search_suggestions_{request.user.id}"
            cache.delete(cache_key)

            return Response(
                {
                    "success": True,
                    "message": "Search recorded successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )

    def delete(self, request):
        """
        Clear user's search history
        Optional Query Parameters:
        - older_than_days: Clear history older than X days
        - search_type: Clear history of specific type
        """
        try:
            serializer = ClearHistoryRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {"success": False, "errors": serializer.errors},
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
                    "success": True,
                    "message": f'Successfully deleted {result["deleted"]} search records',
                    "details": result,
                }
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )


class DeleteSearchEntryAPIView(APIView):
    """Delete a specific search history entry"""

    permission_classes = [IsAuthenticated]

    def delete(self, request, entry_id):
        try:
            success = SearchHistoryService.delete_search_entry(
                entry_id=entry_id, user=request.user
            )

            if success:
                return Response(
                    {"success": True, "message": "Search entry deleted successfully"}
                )
            else:
                return Response(
                    {
                        "success": False,
                        "error": "Search entry not found or you do not have permission",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )


class RecentSearchesAPIView(APIView):
    """Get recent search queries"""

    permission_classes = [IsAuthenticated]

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request):
        """
        Get recent searches
        Query Parameters:
        - limit: Number of results (default: 10)
        - unique: Return unique queries only (default: true)
        """
        try:
            limit = int(request.query_params.get("limit", 10))
            unique = request.query_params.get("unique", "true").lower() == "true"

            recent_searches = SearchHistoryService.get_recent_searches(
                user=request.user, limit=min(limit, 50), unique_queries=unique
            )

            return Response(
                {
                    "success": True,
                    "count": len(recent_searches),
                    "results": recent_searches,
                }
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )


class PopularSearchesAPIView(APIView):
    """Get popular search queries"""

    @method_decorator(cache_page(60 * 30))  # Cache for 30 minutes
    def get(self, request):
        """
        Get popular searches
        Query Parameters:
        - days: Time period in days (default: 7)
        - limit: Number of results (default: 10)
        - search_type: Filter by type
        - user_only: Show only user's popular searches (authenticated only)
        """
        try:
            days = int(request.query_params.get("days", 7))
            limit = int(request.query_params.get("limit", 10))
            search_type = request.query_params.get("search_type")
            user_only = request.query_params.get("user_only", "false").lower() == "true"

            if user_only and request.user.is_authenticated:
                # Get user's popular searches
                popular_searches = SearchHistoryService.get_user_popular_searches(
                    user=request.user, days=min(days, 365), limit=min(limit, 50)
                )
            else:
                # Get global popular searches
                popular_searches = SearchHistoryService.get_popular_searches(
                    days=min(days, 365), limit=min(limit, 50), search_type=search_type
                )

            serializer = PopularSearchSerializer(popular_searches, many=True)

            return Response(
                {
                    "success": True,
                    "count": len(popular_searches),
                    "results": serializer.data,
                }
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )


class SearchSuggestionsAPIView(APIView):
    """Get search suggestions based on prefix"""

    def get(self, request):
        """
        Get search suggestions
        Query Parameters:
        - prefix: Search prefix (required)
        - limit: Number of suggestions (default: 10)
        - include_anonymous: Include anonymous searches (default: false)
        """
        try:
            prefix = request.query_params.get("prefix", "").strip()
            limit = int(request.query_params.get("limit", 10))
            include_anonymous = (
                request.query_params.get("include_anonymous", "false").lower() == "true"
            )

            if not prefix:
                return Response(
                    {"success": False, "error": "Prefix parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Use cache for authenticated users
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
                    cache.set(cache_key, suggestions, 60 * 10)  # Cache for 10 minutes
            else:
                suggestions = SearchHistoryService.get_suggestions(
                    user=None,
                    prefix=prefix,
                    limit=min(limit, 20),
                    include_anonymous=True,
                )

            return Response(
                {
                    "success": True,
                    "count": len(suggestions),
                    "prefix": prefix,
                    "suggestions": suggestions,
                }
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )


class SearchStatisticsAPIView(APIView):
    """Get search statistics"""

    permission_classes = [IsAuthenticated]

    @method_decorator(cache_page(60 * 10))  # Cache for 10 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request):
        """
        Get search statistics
        Query Parameters:
        - days: Time period in days (default: 30)
        """
        try:
            days = int(request.query_params.get("days", 30))

            statistics = SearchHistoryService.get_search_statistics(
                user=request.user, days=min(days, 365)
            )

            serializer = SearchStatisticsSerializer(statistics)

            return Response({"success": True, "statistics": serializer.data})

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )


class SearchTrendsAPIView(APIView):
    """Get search trends over time"""

    @method_decorator(cache_page(60 * 60))  # Cache for 1 hour
    def get(self, request):
        """
        Get search trends
        Query Parameters:
        - days: Time period in days (default: 7)
        - interval: Grouping interval (day/hour) (default: day)
        """
        try:
            days = int(request.query_params.get("days", 7))
            interval = request.query_params.get("interval", "day")

            if interval not in ["day", "hour"]:
                return Response(
                    {
                        "success": False,
                        "error": 'Interval must be either "day" or "hour"',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            trends = SearchHistoryService.get_search_trends(
                days=min(days, 90), interval=interval  # Max 90 days for trends
            )

            return Response(
                {
                    "success": True,
                    "count": len(trends),
                    "interval": interval,
                    "trends": trends,
                }
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )


class ExportSearchHistoryAPIView(APIView):
    """Export user's search history"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Export search history
        Query Parameters:
        - format: Export format (json) (default: json)
        - include_metadata: Include metadata (default: true)
        """
        try:
            export_format = request.query_params.get("format", "json")
            include_metadata = (
                request.query_params.get("include_metadata", "true").lower() == "true"
            )

            if export_format != "json":
                return Response(
                    {
                        "success": False,
                        "error": "Only JSON export format is currently supported",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            export_data = SearchHistoryService.export_user_search_history(
                user=request.user,
                format=export_format,
                include_metadata=include_metadata,
            )

            # Set response headers for file download
            response = Response(export_data)
            response["Content-Disposition"] = (
                f'attachment; filename="search_history_{request.user.username}.json"'
            )
            response["Content-Type"] = "application/json"

            return response

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )
