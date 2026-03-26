from django.urls import path

from stories.views.story import FollowingStoriesView,PopularStoriesView, StoriesByTypeView, StoryCleanupView, StoryDeactivateView, StoryDetailView, StoryExtendView, StoryFeedView, StoryHighlightsView, StoryListView, StoryRecommendationsView, StoryStatsView, StoryViewCountView, UserStoriesView

from stories.views.highlight import StoryHighlightAddStoriesView, StoryHighlightDetailView, StoryHighlightListView, StoryHighlightRemoveStoriesView, StoryHighlightSetCoverView

urlpatterns = [
    # Story CRUD operations
    path('stories/', StoryListView.as_view(), name='story-list'),
    path('stories/<int:story_id>/', StoryDetailView.as_view(), name='story-detail'),
    
    # Story viewing operations
    path('stories/<int:story_id>/view-count/', StoryViewCountView.as_view(), name='story-view-count'),

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
    
    # Admin operations
    path('admin/stories/cleanup/', StoryCleanupView.as_view(), name='story-cleanup'),
    
    
    
    path("highlights/", StoryHighlightListView.as_view(), name="highlights-list"),
    path("highlights/<int:id>/", StoryHighlightDetailView.as_view(), name="highlights-detail"),
    path("highlights/<int:id>/add-stories/", StoryHighlightAddStoriesView.as_view(), name="highlights-add-stories"),
    path("highlights/<int:id>/remove-stories/", StoryHighlightRemoveStoriesView.as_view(), name="highlights-remove-stories"),
    path("highlights/<int:id>/set-cover/", StoryHighlightSetCoverView.as_view(), name="highlights-set-cover"),
]