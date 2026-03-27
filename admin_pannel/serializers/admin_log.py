from rest_framework import serializers
from admin_pannel.models.admin_log import AdminLog
from users.serializers.user.minimal import UserMinimalSerializer


class AdminLogMinimalSerializer(serializers.ModelSerializer):
    """Lightweight list view for admin logs."""
    admin_user = serializers.StringRelatedField(read_only=True)
    target_user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = AdminLog
        fields = ['id', 'admin_user', 'action', 'target_user', 'created_at']
        read_only_fields = fields


class AdminLogCreateSerializer(serializers.ModelSerializer):
    """Used when creating a new admin log entry."""
    class Meta:
        model = AdminLog
        fields = ['admin_user', 'action', 'target_user', 'target_id', 'reason']


class AdminLogDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single admin log entry."""
    admin_user = UserMinimalSerializer(read_only=True)
    target_user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = AdminLog
        fields = '__all__'
        read_only_fields = ['created_at']