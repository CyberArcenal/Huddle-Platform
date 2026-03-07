from django.utils import timezone
from admin_pannel.services.admin_log import AdminLogService
from analytics.services.platform_analytics import PlatformAnalyticsService
from notifications.services.notification import NotificationService   # <-- add this


class ReportedContentStateTransitionService:
    """Handles side effects of report status changes."""

    @staticmethod
    def handle_report_created(report):
        """Called when a new report is submitted."""
        # Increment pending reports count in analytics
        PlatformAnalyticsService.increment_pending_reports()
        # Optionally notify admins (if implemented)

    @staticmethod
    def handle_status_change(report, old_status, new_status):
        """Called when report status changes."""
        # Log the change for audit
        AdminLogService.log_admin_action(
            admin_user=None,  # Could be system if automatic
            action='report_status_change',
            target_id=report.id,
            reason=f'Status changed from {old_status} to {new_status}'
        )

        # Handle specific transitions
        if old_status == 'pending' and new_status in ('resolved', 'dismissed'):
            # Report is resolved or dismissed
            ReportedContentStateTransitionService._handle_report_closed(report, new_status)

        # Update platform analytics (status counts)
        PlatformAnalyticsService.update_report_status_counts(old_status, new_status)

    @staticmethod
    def _handle_report_closed(report, final_status):
        """Handle a report that is resolved or dismissed."""
        # Notify the reporter
        NotificationService.send_report_outcome_notification(
            user=report.reporter,
            report=report,
            outcome=final_status
        )

    @staticmethod
    def handle_report_reviewed(report):
        """Optional: when report is marked as reviewed (in progress)."""
        # Could send notification to reporter that report is being reviewed
        pass