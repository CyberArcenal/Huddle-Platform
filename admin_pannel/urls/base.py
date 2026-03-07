from django.urls import path
from admin_pannel.views import admin_log_views as log_views
from admin_pannel.views import reported_content_views as report_views

urlpatterns = [
    # Admin Logs
    path('logs/', log_views.AdminLogListView.as_view(), name='admin-log-list'),
    path('logs/recent/', log_views.AdminLogRecentView.as_view(), name='admin-log-recent'),
    path('logs/search/', log_views.AdminLogSearchView.as_view(), name='admin-log-search'),
    path('logs/statistics/', log_views.AdminLogStatisticsView.as_view(), name='admin-log-statistics'),
    path('logs/export/', log_views.AdminLogExportView.as_view(), name='admin-log-export'),
    path('logs/cleanup/', log_views.AdminLogCleanupView.as_view(), name='admin-log-cleanup'),
    path('logs/user/<int:user_id>/', log_views.AdminLogUserView.as_view(), name='admin-log-user'),
    path('logs/<int:log_id>/', log_views.AdminLogDetailView.as_view(), name='admin-log-detail'),

    # Admin Actions
    path('actions/ban-user/', log_views.AdminBanUserView.as_view(), name='admin-ban-user'),
    path('actions/warn-user/', log_views.AdminWarnUserView.as_view(), name='admin-warn-user'),
    path('actions/remove-content/', log_views.AdminRemoveContentView.as_view(), name='admin-remove-content'),

    # Reported Content
    path('reports/', report_views.ReportListView.as_view(), name='report-list'),
    path('reports/pending/', report_views.ReportPendingView.as_view(), name='report-pending'),
    path('reports/search/', report_views.ReportSearchView.as_view(), name='report-search'),
    path('reports/statistics/', report_views.ReportStatisticsView.as_view(), name='report-statistics'),
    path('reports/urgent/', report_views.ReportUrgentView.as_view(), name='report-urgent'),
    path('reports/cleanup/', report_views.ReportCleanupView.as_view(), name='report-cleanup'),
    path('reports/moderation-report/', report_views.ReportModerationReportView.as_view(), name='report-moderation'),
    path('reports/user/<int:user_id>/history/', report_views.ReportUserHistoryView.as_view(), name='report-user-history'),
    path('reports/<int:report_id>/', report_views.ReportDetailView.as_view(), name='report-detail'),
    path('reports/<int:report_id>/update-status/', report_views.ReportUpdateStatusView.as_view(), name='report-update-status'),
    path('reports/<int:report_id>/resolve/', report_views.ReportResolveView.as_view(), name='report-resolve'),
    path('reports/<int:report_id>/dismiss/', report_views.ReportDismissView.as_view(), name='report-dismiss'),

    # Public report endpoint
    path('report/', report_views.ReportCreateView.as_view(), name='report-create'),
]

app_name = 'admin_pannel'