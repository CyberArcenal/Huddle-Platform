# search/urls.py
from django.urls import path
from search.views.dedicated import (
    UserSearchView,
    GroupSearchView,
    EventSearchView,
    PostSearchView,
)
from search.views.base import (  # existing history views
    SearchHistoryAPIView,
    DeleteSearchEntryAPIView,
    RecentSearchesAPIView,
    PopularSearchesAPIView,
    SearchSuggestionsAPIView,
    SearchStatisticsAPIView,
    SearchTrendsAPIView,
    ExportSearchHistoryAPIView,
)

urlpatterns = [
    # Dedicated content searches
    path('users/', UserSearchView.as_view(), name='search-users'),
    path('groups/', GroupSearchView.as_view(), name='search-groups'),
    path('events/', EventSearchView.as_view(), name='search-events'),
    path('posts/', PostSearchView.as_view(), name='search-posts'),

    # Existing history endpoints
    path('history/', SearchHistoryAPIView.as_view(), name='search-history'),
    path('history/<int:entry_id>/', DeleteSearchEntryAPIView.as_view(), name='delete-search-entry'),
    path('recent/', RecentSearchesAPIView.as_view(), name='recent-searches'),
    path('popular/', PopularSearchesAPIView.as_view(), name='popular-searches'),
    path('suggestions/', SearchSuggestionsAPIView.as_view(), name='search-suggestions'),
    path('statistics/', SearchStatisticsAPIView.as_view(), name='search-statistics'),
    path('trends/', SearchTrendsAPIView.as_view(), name='search-trends'),
    path('export/', ExportSearchHistoryAPIView.as_view(), name='export-search-history'),
]