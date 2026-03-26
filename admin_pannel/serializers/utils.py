from rest_framework import serializers
from admin_pannel.models.admin_log import AdminLog
from admin_pannel.models.reported_content import ReportedContent
from admin_pannel.services.reported_content import ReportedContentService


# ---------- Input Serializers for Reporting ----------

class ReportStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ReportedContentService.STATUS_CHOICES)
    resolution_notes = serializers.CharField(required=False, allow_blank=True)


class ResolveReportInputSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=[
        ('remove_content', 'Remove Content'),
        ('warn_user', 'Warn User'),
        ('ban_user', 'Ban User'),
        ('dismiss_report', 'Dismiss Report'),
    ])
    resolution_details = serializers.CharField(required=False, allow_blank=True)


# ---------- Input Serializers for Admin Actions ----------
class BanUserInputSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    duration_days = serializers.IntegerField(required=False, allow_null=True)


class WarnUserInputSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    severity = serializers.ChoiceField(choices=['low', 'medium', 'high'], default='low')


class RemoveContentInputSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=['post', 'group'])
    object_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)


# ---------- Filter Serializers ----------
class AdminLogFilterSerializer(serializers.Serializer):
    admin_user_id = serializers.IntegerField(required=False)
    action = serializers.ChoiceField(choices=AdminLog.ACTION_CHOICES, required=False)
    target_user_id = serializers.IntegerField(required=False)
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)


class ReportFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ReportedContentService.STATUS_CHOICES, required=False)
    content_type = serializers.StringRelatedField()
    reporter_id = serializers.IntegerField(required=False)
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    unresolved_only = serializers.BooleanField(default=True)


class SearchAdminLogsSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=100)
    search_in = serializers.MultipleChoiceField(
        choices=['reason', 'admin_username', 'target_username'],
        default=['reason']
    )


# ---------- Statistics Output Serializers ----------
class AdminStatisticsSerializer(serializers.Serializer):
    period_days = serializers.IntegerField()
    total_actions = serializers.IntegerField()
    action_breakdown = serializers.ListField(child=serializers.DictField())
    admin_activity = serializers.ListField(child=serializers.DictField())
    top_targets = serializers.ListField(child=serializers.DictField())
    recent_actions = serializers.ListField(child=serializers.DictField())
    daily_activity = serializers.ListField(child=serializers.DictField())
    most_active_day = serializers.DictField(allow_null=True)
    avg_actions_per_day = serializers.FloatField()


class ReportStatisticsSerializer(serializers.Serializer):
    period_days = serializers.IntegerField()
    total_reports = serializers.IntegerField()
    pending_reports = serializers.IntegerField()
    type_breakdown = serializers.ListField(child=serializers.DictField())
    status_breakdown = serializers.ListField(child=serializers.DictField())
    top_reporters = serializers.ListField(child=serializers.DictField())
    avg_resolution_hours = serializers.FloatField(allow_null=True)
    most_reported_objects = serializers.ListField(child=serializers.DictField())
    resolution_rate = serializers.FloatField()


# ---------- Cleanup / Dismiss Serializers ----------
class CleanupLogsInputSerializer(serializers.Serializer):
    days_to_keep = serializers.IntegerField(default=365, help_text="Delete logs older than this many days")


class DismissReportInputSerializer(serializers.Serializer):
    reason = serializers.CharField(help_text="Reason for dismissal", default="Report dismissed")


class CleanupReportsInputSerializer(serializers.Serializer):
    days_to_keep = serializers.IntegerField(default=180, help_text="Delete reports older than this many days")