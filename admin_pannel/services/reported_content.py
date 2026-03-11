from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from typing import Optional, List, Dict, Any, Tuple

from admin_pannel.models.base import AdminLog
from ..models import ReportedContent, User
import datetime


class ReportedContentService:
    """Service for ReportedContent model operations"""

    STATUS_CHOICES = ["pending", "reviewed", "resolved", "dismissed"]

    @staticmethod
    def report_content(
        reporter: User, content_type: str, object_id: int, reason: str, **extra_fields
    ) -> ReportedContent:
        """Report content (post, comment, user, group)"""
        # Validate content type
        valid_types = [choice[0] for choice in ReportedContent.CONTENT_TYPES]
        if content_type not in valid_types:
            raise ValidationError(f"Content type must be one of {valid_types}")

        # Check if same content was already reported by this user recently
        one_hour_ago = timezone.now() - datetime.timedelta(hours=1)
        recent_report = ReportedContent.objects.filter(
            reporter=reporter,
            content_type=content_type,
            object_id=object_id,
            created_at__gte=one_hour_ago,
        ).first()

        if recent_report:
            raise ValidationError("You have already reported this content recently")

        try:
            with transaction.atomic():
                report = ReportedContent.objects.create(
                    reporter=reporter,
                    content_type=content_type,
                    object_id=object_id,
                    reason=reason,
                    **extra_fields,
                )
                return report
        except IntegrityError as e:
            raise ValidationError(f"Failed to report content: {str(e)}")

    @staticmethod
    def get_report_by_id(report_id: int) -> Optional[ReportedContent]:
        """Retrieve report by ID"""
        try:
            return ReportedContent.objects.get(id=report_id)
        except ReportedContent.DoesNotExist:
            return None

    @staticmethod
    def get_reports(
        status: Optional[str] = None,
        content_type: Optional[str] = None,
        reporter: Optional[User] = None,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        unresolved_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ReportedContent]:
        """Get reported content with filtering options"""
        queryset = ReportedContent.objects.select_related("reporter")

        if status:
            queryset = queryset.filter(status=status)
        elif unresolved_only:
            queryset = queryset.exclude(status__in=["resolved", "dismissed"])

        if content_type:
            queryset = queryset.filter(content_type=content_type)

        if reporter:
            queryset = queryset.filter(reporter=reporter)

        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)

        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        return list(queryset.order_by("-created_at")[offset : offset + limit])

    @staticmethod
    def get_pending_reports(
        content_type: Optional[str] = None, limit: int = 50
    ) -> List[ReportedContent]:
        """Get pending reports that need review"""
        queryset = ReportedContent.objects.filter(status="pending").select_related(
            "reporter"
        )

        if content_type:
            queryset = queryset.filter(content_type=content_type)

        return list(queryset.order_by("created_at")[:limit])

    @staticmethod
    def get_reports_for_content(
        content_type: str, object_id: int, include_resolved: bool = False
    ) -> List[ReportedContent]:
        """Get all reports for a specific piece of content"""
        queryset = ReportedContent.objects.filter(
            content_type=content_type, object_id=object_id
        ).select_related("reporter")

        if not include_resolved:
            queryset = queryset.exclude(status__in=["resolved", "dismissed"])

        return list(queryset.order_by("-created_at"))

    @staticmethod
    def update_report_status(
        report: ReportedContent,
        new_status: str,
        resolved_by: Optional[User] = None,
        resolution_notes: Optional[str] = None,
    ) -> ReportedContent:
        """Update report status"""
        if new_status not in ReportedContentService.STATUS_CHOICES:
            raise ValidationError(
                f"Status must be one of {ReportedContentService.STATUS_CHOICES}"
            )

        # Check if already resolved
        if report.status in ["resolved", "dismissed"]:
            raise ValidationError(f"Report is already {report.status}")

        report.status = new_status

        if new_status in ["resolved", "dismissed"]:
            report.resolved_at = timezone.now()

        if resolution_notes:
            # You might want to add a field for resolution notes
            # For now, we'll append to reason
            report.reason = f"{report.reason}\n\nResolution: {resolution_notes}"

        report.save()
        return report

    @staticmethod
    def resolve_report(
        report: ReportedContent,
        action_taken: str,
        resolved_by: User,
        resolution_details: Optional[str] = None,
    ) -> Tuple[ReportedContent, Dict[str, Any]]:
        """Resolve a report with specific action"""
        # Update report status
        report = ReportedContentService.update_report_status(
            report=report,
            new_status="resolved",
            resolved_by=resolved_by,
            resolution_notes=f"Action: {action_taken}. {resolution_details or ''}",
        )

        # Take action based on report type
        action_result = ReportedContentService._take_content_action(
            report=report, action=action_taken, resolved_by=resolved_by
        )

        return report, action_result

    @staticmethod
    def _take_content_action(
        report: ReportedContent, action: str, resolved_by: User
    ) -> Dict[str, Any]:
        """Take action on reported content"""
        from admin_pannel.services import AdminLogService

        action_result = {
            "report_id": report.id,
            "content_type": report.content_type,
            "object_id": report.object_id,
            "action_taken": action,
            "resolved_by": resolved_by.username,
            "resolved_at": timezone.now(),
            "success": False,
        }

        try:
            if action == "remove_content":
                if report.content_type == "post":
                    # Remove post
                    admin_log, result = AdminLogService.remove_content(
                        admin_user=resolved_by,
                        content_type="post",
                        object_id=report.object_id,
                        reason=f"Reported content: {report.reason[:100]}...",
                    )
                    action_result["success"] = True
                    action_result["details"] = result

                elif report.content_type == "group":
                    # Remove group
                    admin_log, result = AdminLogService.remove_content(
                        admin_user=resolved_by,
                        content_type="group",
                        object_id=report.object_id,
                        reason=f"Reported group: {report.reason[:100]}...",
                    )
                    action_result["success"] = True
                    action_result["details"] = result

            elif action == "warn_user":
                if report.content_type == "user":
                    # Get target user from object_id
                    from users.models import User

                    try:
                        target_user = User.objects.get(id=report.object_id)
                        admin_log, result = AdminLogService.warn_user(
                            admin_user=resolved_by,
                            target_user=target_user,
                            reason=f"Reported user: {report.reason[:100]}...",
                        )
                        action_result["success"] = True
                        action_result["details"] = result
                    except User.DoesNotExist:
                        action_result["error"] = (
                            f"User with ID {report.object_id} not found"
                        )

            elif action == "ban_user":
                if report.content_type == "user":
                    from users.models import User

                    try:
                        target_user = User.objects.get(id=report.object_id)
                        admin_log, result = AdminLogService.ban_user(
                            admin_user=resolved_by,
                            target_user=target_user,
                            reason=f"Reported user: {report.reason[:100]}...",
                        )
                        action_result["success"] = True
                        action_result["details"] = result
                    except User.DoesNotExist:
                        action_result["error"] = (
                            f"User with ID {report.object_id} not found"
                        )

            elif action == "dismiss_report":
                action_result["success"] = True
                action_result["details"] = {
                    "action": "Report dismissed, no action taken"
                }

            else:
                action_result["error"] = f"Unknown action: {action}"

        except Exception as e:
            logger.debug(e)
            logger.debug(e)
            action_result["error"] = str(e)

        return action_result

    @staticmethod
    def dismiss_report(
        report: ReportedContent, dismissed_by: User, reason: str = "Report dismissed"
    ) -> ReportedContent:
        """Dismiss a report as invalid or not requiring action"""
        return ReportedContentService.update_report_status(
            report=report,
            new_status="dismissed",
            resolved_by=dismissed_by,
            resolution_notes=f"Dismissed: {reason}",
        )

    @staticmethod
    def get_report_statistics(
        days: int = 30, content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get statistics about reported content"""
        time_threshold = timezone.now() - datetime.timedelta(days=days)

        queryset = ReportedContent.objects.filter(created_at__gte=time_threshold)

        if content_type:
            queryset = queryset.filter(content_type=content_type)

        # Count by content type
        type_counts = (
            queryset.values("content_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Count by status
        status_counts = (
            queryset.values("status").annotate(count=Count("id")).order_by("-count")
        )

        # Count by reporter (top reporters)
        top_reporters = (
            queryset.values("reporter__username")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        # Resolution time for resolved reports
        resolved_reports = queryset.filter(status="resolved")
        avg_resolution_hours = None
        if resolved_reports.exists():
            total_hours = sum(
                (report.resolved_at - report.created_at).total_seconds() / 3600
                for report in resolved_reports
                if report.resolved_at
            )
            avg_resolution_hours = total_hours / resolved_reports.count()

        # Most reported objects
        most_reported = (
            queryset.values("content_type", "object_id")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        return {
            "period_days": days,
            "total_reports": queryset.count(),
            "pending_reports": queryset.filter(status="pending").count(),
            "type_breakdown": list(type_counts),
            "status_breakdown": list(status_counts),
            "top_reporters": list(top_reporters),
            "avg_resolution_hours": avg_resolution_hours,
            "most_reported_objects": list(most_reported),
            "resolution_rate": (
                (queryset.filter(status="resolved").count() / queryset.count() * 100)
                if queryset.count() > 0
                else 0
            ),
        }

    @staticmethod
    def get_user_report_history(
        user: User,
        as_reporter: bool = True,
        as_content_owner: bool = False,  # This would need additional logic
        limit: int = 50,
    ) -> List[ReportedContent]:
        """Get report history for a user"""
        queryset = ReportedContent.objects.select_related("reporter")

        filters = Q()
        if as_reporter:
            filters |= Q(reporter=user)

        # Note: To get reports where user is the content owner,
        # you'd need to query based on content_type and object_id
        # This is more complex and depends on your content models

        return list(queryset.filter(filters).order_by("-created_at")[:limit])

    @staticmethod
    def is_content_reported(
        content_type: str, object_id: int, threshold: int = 3
    ) -> Tuple[bool, int]:
        """Check if content has been reported multiple times"""
        report_count = ReportedContent.objects.filter(
            content_type=content_type, object_id=object_id, status="pending"
        ).count()

        return report_count >= threshold, report_count

    @staticmethod
    def get_urgent_reports(threshold: int = 5, hours: int = 24) -> List[Dict[str, Any]]:
        """Get urgent reports (multiple reports on same content recently)"""
        time_threshold = timezone.now() - datetime.timedelta(hours=hours)

        # Find content with multiple recent reports
        urgent_content = (
            ReportedContent.objects.filter(
                created_at__gte=time_threshold, status="pending"
            )
            .values("content_type", "object_id")
            .annotate(report_count=Count("id"))
            .filter(report_count__gte=threshold)
            .order_by("-report_count")
        )

        result = []
        for item in urgent_content:
            # Get all reports for this content
            reports = ReportedContent.objects.filter(
                content_type=item["content_type"],
                object_id=item["object_id"],
                created_at__gte=time_threshold,
                status="pending",
            ).select_related("reporter")

            # Get unique reporters
            unique_reporters = set(report.reporter for report in reports)

            result.append(
                {
                    "content_type": item["content_type"],
                    "object_id": item["object_id"],
                    "report_count": item["report_count"],
                    "reports": list(reports),
                    "unique_reporter_count": len(unique_reporters),
                    "first_reported": min(report.created_at for report in reports),
                    "last_reported": max(report.created_at for report in reports),
                }
            )

        return result

    @staticmethod
    def cleanup_old_reports(days_to_keep: int = 180) -> int:
        """Delete resolved/dismissed reports older than specified days"""
        cutoff_date = timezone.now() - datetime.timedelta(days=days_to_keep)

        old_reports = ReportedContent.objects.filter(
            status__in=["resolved", "dismissed"], resolved_at__lt=cutoff_date
        )
        count = old_reports.count()
        old_reports.delete()

        return count

    @staticmethod
    def search_reports(
        query: str,
        search_in: List[str] = ["reason", "reporter_username"],
        limit: int = 50,
    ) -> List[ReportedContent]:
        """Search reported content"""
        filters = Q()

        if "reason" in search_in:
            filters |= Q(reason__icontains=query)

        if "reporter_username" in search_in:
            filters |= Q(reporter__username__icontains=query)

        return list(
            ReportedContent.objects.filter(filters)
            .select_related("reporter")
            .order_by("-created_at")[:limit]
        )

    @staticmethod
    def generate_moderation_report(
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
    ) -> Dict[str, Any]:
        """Generate moderation report for a time period"""
        if not start_date:
            start_date = timezone.now() - datetime.timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        # Get reports in period
        reports = ReportedContent.objects.filter(
            created_at__gte=start_date, created_at__lte=end_date
        )

        # Get admin logs in period
        from admin_pannel.services import AdminLogService

        admin_logs = AdminLog.objects.filter(
            created_at__gte=start_date, created_at__lte=end_date
        )

        # Calculate statistics
        total_reports = reports.count()
        resolved_reports = reports.filter(status="resolved").count()
        pending_reports = reports.filter(status="pending").count()

        # Action breakdown
        action_breakdown = (
            admin_logs.values("action").annotate(count=Count("id")).order_by("-count")
        )

        # Top moderators
        top_moderators = (
            admin_logs.values("admin_user__username")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        # Resolution time analysis
        resolved_with_time = reports.filter(
            status="resolved", resolved_at__isnull=False
        )

        resolution_times = []
        for report in resolved_with_time:
            if report.resolved_at:
                hours = (report.resolved_at - report.created_at).total_seconds() / 3600
                resolution_times.append(hours)

        avg_resolution_time = (
            sum(resolution_times) / len(resolution_times) if resolution_times else 0
        )

        return {
            "period": {
                "start": start_date,
                "end": end_date,
                "days": (end_date - start_date).days,
            },
            "report_statistics": {
                "total_reports": total_reports,
                "resolved_reports": resolved_reports,
                "pending_reports": pending_reports,
                "resolution_rate": (
                    (resolved_reports / total_reports * 100) if total_reports > 0 else 0
                ),
                "avg_resolution_hours": avg_resolution_time,
            },
            "moderation_actions": {
                "total_actions": admin_logs.count(),
                "action_breakdown": list(action_breakdown),
                "top_moderators": list(top_moderators),
            },
            "trends": {
                "reports_per_day": total_reports / max(1, (end_date - start_date).days),
                "actions_per_day": admin_logs.count()
                / max(1, (end_date - start_date).days),
            },
            "generated_at": timezone.now(),
        }
