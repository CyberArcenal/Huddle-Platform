# urls.py
from django.urls import path

from search.views.base import (
    DeleteSearchEntryAPIView,
    ExportSearchHistoryAPIView,
    PopularSearchesAPIView,
    RecentSearchesAPIView,
    SearchHistoryAPIView,
    SearchStatisticsAPIView,
    SearchSuggestionsAPIView,
    SearchTrendsAPIView,
)

urlpatterns = [
    # Main search history endpoint
    path("history/", SearchHistoryAPIView.as_view(), name="search-history"),
    # Delete specific entry
    path(
        "history/<int:entry_id>/delete/",
        DeleteSearchEntryAPIView.as_view(),
        name="delete-search-entry",
    ),
    # Recent searches
    path("recent/", RecentSearchesAPIView.as_view(), name="recent-searches"),
    # Popular searches (global and user-specific)
    path("popular/", PopularSearchesAPIView.as_view(), name="popular-searches"),
    # Search suggestions
    path("suggestions/", SearchSuggestionsAPIView.as_view(), name="search-suggestions"),
    # Search statistics
    path("statistics/", SearchStatisticsAPIView.as_view(), name="search-statistics"),
    # Search trends
    path("trends/", SearchTrendsAPIView.as_view(), name="search-trends"),
    # Export search history
    path("export/", ExportSearchHistoryAPIView.as_view(), name="export-search-history"),
]
