from rest_framework import serializers
from groups.models.group import GROUP_PRIVACY_CHOICES, Group
from groups.services.group_member import GroupMemberService
from users.models import User


class GroupSearchSerializer(serializers.Serializer):
    """Serializer for group search parameters."""

    query = serializers.CharField(required=False)
    privacy = serializers.ChoiceField(choices=GROUP_PRIVACY_CHOICES, required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)
    offset = serializers.IntegerField(min_value=0, default=0)


class GroupStatisticsSerializer(serializers.Serializer):
    """Serializer for group statistics output."""

    total_members = serializers.IntegerField()
    admin_count = serializers.IntegerField()
    moderator_count = serializers.IntegerField()
    member_count = serializers.IntegerField()
    recent_joins_7d = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    privacy = serializers.CharField()
    creator = serializers.CharField()


class TransferOwnershipSerializer(serializers.Serializer):
    """Serializer for transferring group ownership."""

    new_owner_id = serializers.IntegerField()

    def validate(self, data):
        group = self.context.get("group")
        current_owner = self.context.get("current_owner")

        try:
            new_owner = User.objects.get(id=data["new_owner_id"])
        except User.DoesNotExist:
            raise serializers.ValidationError("New owner does not exist")

        if not GroupMemberService.is_member(group, new_owner):
            raise serializers.ValidationError("New owner must be a group member")

        data["new_owner"] = new_owner
        return data
