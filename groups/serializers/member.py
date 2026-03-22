from rest_framework import serializers
from django.core.exceptions import ValidationError

from groups.models.member import GROUP_ROLE_CHOICES, GroupMember
from groups.services.group_member import GroupMemberService
from users.models import User
from users.serializers.user import UserMinimalSerializer


class GroupMemberMinimalSerializer(serializers.ModelSerializer):
    """Lightweight member info for lists."""
    user = UserMinimalSerializer(read_only=True)
    role = serializers.ChoiceField(choices=GROUP_ROLE_CHOICES)

    class Meta:
        model = GroupMember
        fields = ['id', 'user', 'role', 'joined_at']
        read_only_fields = fields


class GroupMemberCreateSerializer(serializers.Serializer):
    """Serializer for adding a member to a group."""
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=GROUP_ROLE_CHOICES, default='member')

    def validate(self, data):
        group = self.context.get('group')
        request_user = self.context.get('request').user

        if not group:
            raise serializers.ValidationError("Group context required")

        try:
            user = User.objects.get(id=data['user_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist")

        if GroupMemberService.is_member(group, user):
            raise serializers.ValidationError("User is already a member")

        # Check permissions
        if group.creator != request_user:
            requester_membership = GroupMemberService.get_membership(group, request_user)
            if not requester_membership or requester_membership.role not in ['admin', 'moderator']:
                raise serializers.ValidationError("Only admins and moderators can add members")

        # Role assignment restrictions
        if data['role'] in ['admin', 'moderator'] and group.creator != request_user:
            raise serializers.ValidationError("Only group creator can assign admin/moderator roles")

        data['user'] = user
        return data

    def create(self, validated_data):
        group = self.context['group']
        user = validated_data['user']
        role = validated_data['role']

        try:
            return GroupMemberService.add_member(group, user, role)
        except ValidationError as e:
            raise serializers.ValidationError(str(e))


class GroupMemberDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a group member."""
    user = UserMinimalSerializer(read_only=True)
    is_creator = serializers.SerializerMethodField()

    class Meta:
        model = GroupMember
        fields = [
            'id', 'user',
            'role', 'joined_at', 'is_creator'
        ]
        read_only_fields = ['user_id', 'joined_at', 'is_creator']

    def get_is_creator(self, obj) -> bool:
        return obj.group.creator == obj.user


class GroupMemberUpdateSerializer(serializers.Serializer):
    """Serializer for updating a member's role."""
    role = serializers.ChoiceField(choices=GROUP_ROLE_CHOICES)

    def validate(self, data):
        group = self.context.get('group')
        target_user = self.context.get('target_user')
        request_user = self.context.get('request').user

        if not GroupMemberService.is_member(group, target_user):
            raise serializers.ValidationError("Target user is not a member")

        # Check permissions
        if group.creator != request_user:
            requester_membership = GroupMemberService.get_membership(group, request_user)
            if not requester_membership or requester_membership.role != 'admin':
                raise serializers.ValidationError("Only admins can change member roles")

        # Prevent changing creator's role
        if group.creator == target_user:
            raise serializers.ValidationError("Cannot change creator's role")

        return data

    def update(self, instance, validated_data):
        # instance here is the GroupMember object to update
        instance.role = validated_data['role']
        instance.save()
        return instance