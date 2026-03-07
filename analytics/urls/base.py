from django.urls import path
from analytics.views import platform_analytics_views as platform_views
from analytics.views import user_analytics_views as user_views

urlpatterns = [
    # Platform analytics
    path('platform/daily/', platform_views.PlatformAnalyticsDailyView.as_view(), name='platform-daily'),
    path('platform/range/', platform_views.PlatformAnalyticsRangeView.as_view(), name='platform-range'),
    path('platform/summary/', platform_views.PlatformAnalyticsSummaryView.as_view(), name='platform-summary'),
    path('platform/trends/', platform_views.PlatformAnalyticsTrendsView.as_view(), name='platform-trends'),
    path('platform/health/', platform_views.PlatformAnalyticsHealthView.as_view(), name='platform-health'),
    path('platform/top-days/', platform_views.PlatformAnalyticsTopDaysView.as_view(), name='platform-top-days'),
    path('platform/correlation/', platform_views.PlatformAnalyticsCorrelationView.as_view(), name='platform-correlation'),
    path('platform/report/', platform_views.PlatformAnalyticsReportView.as_view(), name='platform-report'),
    path('platform/cleanup/', platform_views.PlatformAnalyticsCleanupView.as_view(), name='platform-cleanup'),

    # User analytics
    path('user/daily/', user_views.UserAnalyticsDailyView.as_view(), name='user-daily'),
    path('user/daily/<int:user_id>/', user_views.UserAnalyticsDailyView.as_view(), name='user-daily-specific'),
    path('user/range/', user_views.UserAnalyticsRangeView.as_view(), name='user-range'),
    path('user/range/<int:user_id>/', user_views.UserAnalyticsRangeView.as_view(), name='user-range-specific'),
    path('user/summary/', user_views.UserAnalyticsSummaryView.as_view(), name='user-summary'),
    path('user/summary/<int:user_id>/', user_views.UserAnalyticsSummaryView.as_view(), name='user-summary-specific'),
    path('user/trends/', user_views.UserAnalyticsTrendsView.as_view(), name='user-trends'),
    path('user/trends/<int:user_id>/', user_views.UserAnalyticsTrendsView.as_view(), name='user-trends-specific'),
    path('user/engagement/', user_views.UserAnalyticsEngagementView.as_view(), name='user-engagement'),
    path('user/engagement/<int:user_id>/', user_views.UserAnalyticsEngagementView.as_view(), name='user-engagement-specific'),
    path('user/top-days/', user_views.UserAnalyticsTopDaysView.as_view(), name='user-top-days'),
    path('user/top-days/<int:user_id>/', user_views.UserAnalyticsTopDaysView.as_view(), name='user-top-days-specific'),
    path('user/compare/', user_views.UserAnalyticsCompareView.as_view(), name='user-compare'),
    path('user/cleanup/', user_views.UserAnalyticsCleanupView.as_view(), name='user-cleanup'),
]

app_name = 'analytics'