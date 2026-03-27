from typing import Optional

from rest_framework import serializers
from django.core.exceptions import ValidationError
from groups.models.group import GROUP_PRIVACY_CHOICES, GROUP_TYPE_CHOICES, Group
from groups.services.group import GroupService
from groups.services.group_member import GroupMemberService
from groups.serializers.member import GroupMemberMinimalSerializer

class GroupMemberPreviewSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    profile_picture = serializers.CharField(allow_null=True)

class GroupMinimalSerializer(serializers.ModelSerializer):
    group_type_display = serializers.CharField(source='get_group_type_display', read_only=True)

    # Extra display fields
    short_description = serializers.SerializerMethodField()
    formatted_member_count = serializers.SerializerMethodField()
    member_preview = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            'id',
            'name',
            'profile_picture',
            'member_count',
            'group_type',
            'group_type_display',
            'short_description',
            'formatted_member_count',
            'member_preview',
            'is_member'
        ]
        read_only_fields = fields

    def get_short_description(self, obj) -> str:
        desc = getattr(obj, 'description', '') or ''
        max_len = 120
        if len(desc) <= max_len:
            return desc
        return desc[:max_len].rsplit(' ', 1)[0] + '…'

    def get_formatted_member_count(self, obj) -> str:
        try:
            n = int(getattr(obj, 'member_count', 0) or 0)
        except Exception:
            n = 0
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}k"
        return str(n)

    def get_member_preview(self, obj) -> GroupMemberMinimalSerializer(many=True): # type: ignore
        """Return up to 3 preview members serialized."""
        members_qs = getattr(obj, 'members_preview', None)
        if not members_qs:
            return []
        serializer = GroupMemberMinimalSerializer(members_qs[:3], many=True, context=self.context)
        return serializer.data

    def get_is_member(self, obj) -> bool:
        request = self.context.get('request', None)
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        # Use annotated attribute if present
        if hasattr(obj, 'is_member_for_user'):
            return bool(getattr(obj, 'is_member_for_user'))
        # Fallback: check membership (may hit DB)
        try:
            return obj.memberships.filter(user_id=user.id).exists()
        except Exception:
            return False



class GroupCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating groups."""
    class Meta:
        model = Group
        fields = [
            'name', 'description', 'privacy', 'group_type',
            'profile_picture', 'cover_photo'
        ]

    def validate_name(self, value):
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

    def validate_group_type(self, value):
        valid_types = [choice[0] for choice in GROUP_TYPE_CHOICES]
        if value not in valid_types:
            raise serializers.ValidationError(f"Group type must be one of {valid_types}")
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
                group_type=validated_data.get('group_type', 'hobby'),
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
    """Detailed view for a single group with member display details."""
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    creator_id = serializers.IntegerField(source='creator.id', read_only=True)
    is_member = serializers.SerializerMethodField()
    member_role = serializers.SerializerMethodField()
    group_type_display = serializers.CharField(source='get_group_type_display', read_only=True)
    member_preview = serializers.SerializerMethodField()
    formatted_member_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            'id', 'name', 'description', 'creator', 'creator_username', 'creator_id',
            'profile_picture', 'cover_photo', 'privacy', 'group_type', 'group_type_display',
            'member_count', 'formatted_member_count', 'created_at', 'is_member', 'member_role',
            'member_preview'
        ]
        read_only_fields = ['creator', 'member_count', 'created_at']

    def get_is_member(self, obj) -> bool:
        """
        Prefer annotated attribute is_member_for_user to avoid DB hits.
        Fallback to GroupMemberService check if annotation not present.
        """
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        # Use annotated boolean if present
        if hasattr(obj, 'is_member_for_user'):
            return bool(getattr(obj, 'is_member_for_user'))

        # Fallback to service (should be cached or efficient)
        try:
            return GroupMemberService.is_member(obj, user)
        except Exception:
            # Conservative default
            return False

    def get_member_role(self, obj) -> Optional[str]:
        """
        Prefer annotated member_role_for_user (string) to avoid DB hits.
        Fallback to GroupMemberService.get_membership.
        Returns role string like 'admin', 'moderator', 'member' or None.
        """
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None

        if hasattr(obj, 'member_role_for_user'):
            return getattr(obj, 'member_role_for_user') or None

        try:
            membership = GroupMemberService.get_membership(obj, user)
            return membership.role if membership else None
        except Exception:
            return None

    def get_member_preview(self, obj) -> GroupMemberMinimalSerializer(many=True): # type: ignore
        """Return up to 3 preview members serialized."""
        members_qs = getattr(obj, 'members_preview', None)
        if not members_qs:
            return []
        serializer = GroupMemberMinimalSerializer(members_qs[:3], many=True, context=self.context)
        return serializer.data

    def get_formatted_member_count(self, obj) -> str:
        try:
            n = int(getattr(obj, 'member_count', 0) or 0)
        except Exception:
            n = 0
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}k"
        return str(n)
