from django.urls import path

from stories.views.base import FollowingStoriesView, MutualStoryViewsView, PopularStoriesView, StoriesByTypeView, StoryCleanupView, StoryDeactivateView, StoryDetailView, StoryExtendView, StoryFeedView, StoryHighlightsView, StoryListView, StoryRecentViewersView, StoryRecommendationsView, StoryStatsView, StoryViewCountView, StoryViewCreateView, StoryViewStatsView, StoryViewsListView, UserStoriesView

urlpatterns = [
    # Story CRUD operations
    path('stories/', StoryListView.as_view(), name='story-list'),
    path('stories/<int:story_id>/', StoryDetailView.as_view(), name='story-detail'),
    
    # Story viewing operations
    path('stories/<int:story_id>/view/', StoryViewCreateView.as_view(), name='story-view-create'),
    path('stories/<int:story_id>/views/', StoryViewsListView.as_view(), name='story-views-list'),
    path('stories/<int:story_id>/view-count/', StoryViewCountView.as_view(), name='story-view-count'),
    path('stories/<int:story_id>/recent-viewers/', StoryRecentViewersView.as_view(), name='story-recent-viewers'),
    
    # Story actions
    path('stories/<int:story_id>/deactivate/', StoryDeactivateView.as_view(), name='story-deactivate'),
    path('stories/<int:story_id>/extend/', StoryExtendView.as_view(), name='story-extend'),
    
    # User stories
    path('users/<int:user_id>/stories/', UserStoriesView.as_view(), name='user-stories'),
    path('me/stories/', UserStoriesView.as_view(), name='my-stories'),
    
    # Story feeds and discovery
    path('stories/feed/', StoryFeedView.as_view(), name='story-feed'),
    path('stories/following/', FollowingStoriesView.as_view(), name='following-stories'),
    path('stories/highlights/', StoryHighlightsView.as_view(), name='story-highlights'),
    path('stories/recommendations/', StoryRecommendationsView.as_view(), name='story-recommendations'),
    path('stories/popular/', PopularStoriesView.as_view(), name='popular-stories'),
    
    # Stories by type
    path('stories/type/<str:story_type>/', StoriesByTypeView.as_view(), name='stories-by-type'),
    
    # Statistics
    path('stories/stats/', StoryStatsView.as_view(), name='story-stats'),
    path('stories/view-stats/', StoryViewStatsView.as_view(), name='story-view-stats'),
    path('users/<int:other_user_id>/mutual-views/', MutualStoryViewsView.as_view(), name='mutual-story-views'),
    
    # Admin operations
    path('admin/stories/cleanup/', StoryCleanupView.as_view(), name='story-cleanup'),
]