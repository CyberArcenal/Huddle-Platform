# search/urls.py
from django.urls import path
from search.views.dedicated_search import (
    GroupSearchView,
    EventSearchView,
    PostSearchView,
)
from search.views.user_search import AdvancedUserSearchView, GlobalSearchView, SearchAutocompleteView, SearchByEmailView, SearchByUsernameView, UserSearchView
from search.views.search_history import (  # existing history views
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
    
    path('groups/', GroupSearchView.as_view(), name='search-groups'),
    path('events/', EventSearchView.as_view(), name='search-events'),
    path('posts/', PostSearchView.as_view(), name='search-posts'),
    
    # Search endpoints
    path('users/', UserSearchView.as_view(), name='search-users'),
    path('search/advanced/', AdvancedUserSearchView.as_view(), name='advanced-search'),
    path('search/autocomplete/', SearchAutocompleteView.as_view(), name='search-autocomplete'),
    path('search/by-username/', SearchByUsernameView.as_view(), name='search-by-username'),
    path('search/by-email/', SearchByEmailView.as_view(), name='search-by-email'),
    path('search/global/', GlobalSearchView.as_view(), name='global-search'),

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