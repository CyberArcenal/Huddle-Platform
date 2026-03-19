from typing import Optional

from rest_framework import serializers
from django.core.exceptions import ValidationError
from groups.models.group import GROUP_PRIVACY_CHOICES, Group
from groups.models.member import MemberRole
from groups.services.group import GroupService
from groups.services.group_member import GroupMemberService
from users.models import User


class GroupMinimalSerializer(serializers.ModelSerializer):
    """Lightweight group info for listings."""
    class Meta:
        model = Group
        fields = ['id', 'name', 'profile_picture', 'member_count']
        read_only_fields = fields


class GroupCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating groups."""
    class Meta:
        model = Group
        fields = ['name', 'description', 'privacy', 'profile_picture', 'cover_photo']

    def validate_name(self, value):
        # Check uniqueness, excluding current instance
        instance = getattr(self, 'instance', None)
        qs = Group.objects.all()
        if instance:
            qs = qs.exclude(id=instance.id)
        if qs.filter(name=value).exists():
            raise serializers.ValidationError("A group with this name already exists")
        return value

    def validate_privacy(self, value):
        valid_privacy = [choice[0] for choice in GROUP_PRIVACY_CHOICES]
        if value not in valid_privacy:
            raise serializers.ValidationError(f"Privacy must be one of {valid_privacy}")
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        creator = request.user if request else None
        if not creator:
            raise serializers.ValidationError("User must be authenticated")

        try:
            return GroupService.create_group(
                creator=creator,
                name=validated_data['name'],
                description=validated_data.get('description'),
                privacy=validated_data.get('privacy', 'public'),
                profile_picture=validated_data.get('profile_picture'),
                cover_photo=validated_data.get('cover_photo')
            )
        except ValidationError as e:
            raise serializers.ValidationError(e.message_dict)

    def update(self, instance, validated_data):
        request = self.context.get('request')
        if not request:
            raise serializers.ValidationError("Request context required")

        # Permission check: only creator or admin can update
        if instance.creator != request.user:
            membership = GroupMemberService.get_membership(instance, request.user)
            if not membership or membership.role != 'admin':
                raise serializers.ValidationError("Only admins can update group details")

        # Update fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class GroupDisplaySerializer(serializers.ModelSerializer):
    """Detailed view for a single group."""
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    creator_id = serializers.IntegerField(source='creator.id', read_only=True)
    is_member = serializers.SerializerMethodField()
    member_role = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            'id', 'name', 'description', 'creator', 'creator_username', 'creator_id',
            'profile_picture', 'cover_photo', 'privacy', 'member_count',
            'created_at', 'is_member', 'member_role'
        ]
        read_only_fields = ['creator', 'member_count', 'created_at']

    def get_is_member(self, obj) -> bool:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return GroupMemberService.is_member(obj, request.user)
        return False

    def get_member_role(self, obj) -> Optional[MemberRole]:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            membership = GroupMemberService.get_membership(obj, request.user)
            return membership.role if membership else None
        return None