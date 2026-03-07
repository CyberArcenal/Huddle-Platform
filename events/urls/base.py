from django.urls import path, include
from events import views
from events.views import event_analytics
# Event URL patterns
event_urlpatterns = [
    # Main event endpoints
    path('', views.EventListView.as_view(), name='event-list'),
    path('create/', views.EventCreateView.as_view(), name='event-create'),
    path('upcoming/', views.UpcomingEventsView.as_view(), name='upcoming-events'),
    path('past/', views.PastEventsView.as_view(), name='past-events'),
    path('search/', views.EventSearchView.as_view(), name='event-search'),
    path('featured/', views.FeaturedEventsView.as_view(), name='featured-events'),
    path('recommended/', views.RecommendedEventsView.as_view(), name='recommended-events'),
    path('timeline/', views.EventTimelineView.as_view(), name='event-timeline'),
    
    # Event type endpoints
    path('type/<str:event_type>/', views.EventTypeEventsView.as_view(), name='events-by-type'),
    
    # User organized events
    path('organized/', views.UserOrganizedEventsView.as_view(), name='user-organized-events'),
    path('organized/<int:user_id>/', views.UserOrganizedEventsView.as_view(), name='user-organized-events-detail'),
    
    # Group events
    path('group/<int:group_id>/', views.GroupEventsView.as_view(), name='group-events'),
]

# Event detail URL patterns (with event ID)
event_detail_urlpatterns = [
    path('', views.EventDetailView.as_view(), name='event-detail'),
    path('update/', views.EventUpdateView.as_view(), name='event-update'),
    path('delete/', views.EventDeleteView.as_view(), name='event-delete'),
    path('statistics/', views.EventStatisticsView.as_view(), name='event-statistics'),
    
    # Attendance endpoints for this event
    path('attendees/', views.EventAttendanceListView.as_view(), name='event-attendees'),
    path('attendees/mutual/', views.MutualAttendeesView.as_view(), name='mutual-attendees'),
    path('attendees/trend/', views.AttendanceTrendView.as_view(), name='attendance-trend'),
    path('attendees/reminders/', views.SendRemindersView.as_view(), name='send-reminders'),
    
    # RSVP endpoints
    path('rsvp/', views.EventRSVPView.as_view(), name='event-rsvp'),
    path('rsvp/status/', views.UpdateAttendanceStatusView.as_view(), name='update-attendance-status'),
    
    # Specific attendance records
    path('attendance/', views.EventAttendanceDetailView.as_view(), name='event-attendance-self'),
    path('attendance/<int:user_id>/', views.EventAttendanceDetailView.as_view(), name='event-attendance-user'),
]

# User events URL patterns
user_events_urlpatterns = [
    path('', views.UserEventsView.as_view(), name='user-events'),
    path('<int:user_id>/', views.UserEventsView.as_view(), name='user-events-detail'),
    path('statistics/', views.UserAttendanceStatisticsView.as_view(), name='user-attendance-statistics'),
    path('statistics/<int:user_id>/', views.UserAttendanceStatisticsView.as_view(), name='user-attendance-statistics-detail'),
]

# Main URL patterns
urlpatterns = [
    # Event endpoints
    path('events/', include(event_urlpatterns)),
    path('events/<int:pk>/', include(event_detail_urlpatterns)),
    
    # User events endpoints
    path('user/events/', include(user_events_urlpatterns)),
    
        path('events/<int:event_id>/analytics/', event_analytics.EventAnalyticsListView.as_view(), name='event-analytics-list'),
    path('events/<int:event_id>/analytics/<str:date>/', event_analytics.EventAnalyticsDetailView.as_view(), name='event-analytics-detail'),
    path('events/<int:event_id>/analytics/summary/', event_analytics.EventAnalyticsSummaryView.as_view(), name='event-analytics-summary'),
]

# For backward compatibility (optional)
legacy_urlpatterns = [
    path('', views.EventListView.as_view(), name='event-list-legacy'),
    path('<int:pk>/', views.EventDetailView.as_view(), name='event-detail-legacy'),
    path('<int:pk>/attendees/', views.EventAttendanceListView.as_view(), name='event-attendees-legacy'),
    path('<int:event_id>/rsvp/', views.EventRSVPView.as_view(), name='event-rsvp-legacy'),
]

# Uncomment if you need legacy endpoints
# urlpatterns += legacy_urlpatterns