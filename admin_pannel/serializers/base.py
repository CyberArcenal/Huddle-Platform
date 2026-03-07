from rest_framework import serializers
from admin_pannel.models.base import AdminLog, ReportedContent
from admin_pannel.services.reported_content import ReportedContentService
from users.models import User
from users.serializers.user import UserMinimalSerializer

# ---------- Model Serializers ----------
class AdminLogSerializer(serializers.ModelSerializer):
    admin_user = UserMinimalSerializer(read_only=True)
    target_user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = AdminLog
        fields = '__all__'


class ReportedContentSerializer(serializers.ModelSerializer):
    reporter = UserMinimalSerializer(read_only=True)
    content_type_display = serializers.CharField(
        source='get_content_type_display', read_only=True
    )

    class Meta:
        model = ReportedContent
        fields = '__all__'


# ---------- Input Serializers for Reporting ----------
class ReportContentInputSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=ReportedContent.CONTENT_TYPES)
    object_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)


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
    severity = serializers.ChoiceField(
        choices=['low', 'medium', 'high'], default='low'
    )


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
    status = serializers.ChoiceField(
        choices=ReportedContentService.STATUS_CHOICES, required=False
    )
    content_type = serializers.ChoiceField(
        choices=ReportedContent.CONTENT_TYPES, required=False
    )
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