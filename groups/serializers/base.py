from rest_framework import serializers
from django.core.exceptions import ValidationError

from groups.models.base import Group, GroupMember
from groups.services.group import GroupService
from groups.services.group_member import GroupMemberService
from users.models.base import User

class GroupMinimalSerializer(serializers.ModelSerializer):
    """Minimal group serializer for nested representations"""
    
    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'profile_picture', 'creator', 'creator_id']
        read_only_fields = fields
        
        
class GroupSerializer(serializers.ModelSerializer):
    """Serializer for Group model"""
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
    
    def get_is_member(self, obj):
        """Check if current user is a member of the group"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return GroupMemberService.is_member(obj, request.user)
        return False
    
    def get_member_role(self, obj):
        """Get current user's role in the group if member"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            membership = GroupMemberService.get_membership(obj, request.user)
            return membership.role if membership else None
        return None
    
    def validate_name(self, value):
        """Validate group name uniqueness"""
        if self.instance and self.instance.name == value:
            return value
        
        if Group.objects.filter(name=value).exists():
            raise serializers.ValidationError("A group with this name already exists")
        return value
    
    def validate_privacy(self, value):
        """Validate privacy choice"""
        valid_privacy = [choice[0] for choice in Group.PRIVACY_CHOICES]
        if value not in valid_privacy:
            raise serializers.ValidationError(
                f"Privacy must be one of {valid_privacy}"
            )
        return value


class GroupCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating groups"""
    class Meta:
        model = Group
        fields = ['name', 'description', 'privacy', 'profile_picture', 'cover_photo']
    
    def create(self, validated_data):
        """Create a new group using GroupService"""
        request = self.context.get('request')
        creator = request.user if request else None
        
        if not creator:
            raise serializers.ValidationError("User must be authenticated")
        
        try:
            group = GroupService.create_group(
                creator=creator,
                name=validated_data.get('name'),
                description=validated_data.get('description'),
                privacy=validated_data.get('privacy', 'public'),
                profile_picture=validated_data.get('profile_picture'),
                cover_photo=validated_data.get('cover_photo')
            )
            return group
        except ValidationError as e:
            raise serializers.ValidationError(e.message_dict)


class GroupUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating groups"""
    class Meta:
        model = Group
        fields = ['name', 'description', 'privacy', 'profile_picture', 'cover_photo']
    
    def validate(self, data):
        """Validate update data"""
        instance = self.instance
        request = self.context.get('request')
        
        if not instance:
            return data
        
        # Check if user is creator or admin
        if instance.creator != request.user:
            membership = GroupMemberService.get_membership(instance, request.user)
            if not membership or membership.role != 'admin':
                raise serializers.ValidationError(
                    "Only admins can update group details"
                )
        
        return data


class GroupMemberSerializer(serializers.ModelSerializer):
    """Serializer for GroupMember model"""
    user_id = serializers.IntegerField(source='user.id')
    username = serializers.CharField(source='user.username')
    email = serializers.EmailField(source='user.email', required=False)
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    is_creator = serializers.SerializerMethodField()
    
    class Meta:
        model = GroupMember
        fields = [
            'id', 'user_id', 'username', 'email', 'first_name', 'last_name',
            'role', 'joined_at', 'is_creator'
        ]
        read_only_fields = ['user_id', 'username', 'email', 'joined_at', 'is_creator']
    
    def get_is_creator(self, obj):
        """Check if member is the group creator"""
        return obj.group.creator == obj.user


class GroupMemberCreateSerializer(serializers.Serializer):
    """Serializer for adding members to groups"""
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(
        choices=GroupMember.ROLE_CHOICES,
        default='member'
    )
    
    def validate(self, data):
        """Validate member addition"""
        group = self.context.get('group')
        request_user = self.context.get('request').user
        
        if not group:
            raise serializers.ValidationError("Group context is required")
        
        # Get user
        try:
            user = User.objects.get(id=data['user_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist")
        
        # Check if already member
        if GroupMemberService.is_member(group, user):
            raise serializers.ValidationError("User is already a member")
        
        # Check permissions
        if group.creator != request_user:
            requester_membership = GroupMemberService.get_membership(group, request_user)
            if not requester_membership or requester_membership.role not in ['admin', 'moderator']:
                raise serializers.ValidationError(
                    "Only admins and moderators can add members"
                )
        
        # Validate role assignment
        if data['role'] in ['admin', 'moderator']:
            if group.creator != request_user:
                raise serializers.ValidationError(
                    "Only group creator can assign admin/moderator roles"
                )
        
        data['user'] = user
        return data


class GroupMemberUpdateSerializer(serializers.Serializer):
    """Serializer for updating member roles"""
    role = serializers.ChoiceField(choices=GroupMember.ROLE_CHOICES)
    
    def validate(self, data):
        """Validate role update"""
        group = self.context.get('group')
        target_user = self.context.get('target_user')
        request_user = self.context.get('request').user
        
        # Check if target is member
        if not GroupMemberService.is_member(group, target_user):
            raise serializers.ValidationError("Target user is not a member")
        
        # Check permissions
        if group.creator != request_user:
            requester_membership = GroupMemberService.get_membership(group, request_user)
            if not requester_membership or requester_membership.role != 'admin':
                raise serializers.ValidationError(
                    "Only admins can change member roles"
                )
        
        # Prevent changing creator's role
        if group.creator == target_user:
            raise serializers.ValidationError("Cannot change creator's role")
        
        return data


class GroupSearchSerializer(serializers.Serializer):
    """Serializer for group search"""
    query = serializers.CharField(required=False)
    privacy = serializers.ChoiceField(
        choices=Group.PRIVACY_CHOICES,
        required=False
    )
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)
    offset = serializers.IntegerField(min_value=0, default=0)


class GroupStatisticsSerializer(serializers.Serializer):
    """Serializer for group statistics"""
    total_members = serializers.IntegerField()
    admin_count = serializers.IntegerField()
    moderator_count = serializers.IntegerField()
    member_count = serializers.IntegerField()
    recent_joins_7d = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    privacy = serializers.CharField()
    creator = serializers.CharField()


class TransferOwnershipSerializer(serializers.Serializer):
    """Serializer for transferring group ownership"""
    new_owner_id = serializers.IntegerField()
    
    def validate(self, data):
        """Validate ownership transfer"""
        group = self.context.get('group')
        current_owner = self.context.get('current_owner')
        
        try:
            new_owner = User.objects.get(id=data['new_owner_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError("New owner does not exist")
        
        # Check if new owner is member
        if not GroupMemberService.is_member(group, new_owner):
            raise serializers.ValidationError("New owner must be a group member")
        
        data['new_owner'] = new_owner
        return data