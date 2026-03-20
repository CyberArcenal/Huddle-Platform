from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Q
from typing import Optional, List, Dict, Any, Tuple

from feed.models.post import Post
from groups.models.group import GROUP_PRIVACY_CHOICES
from users.models.user import User
from ..models import Group
import uuid


class GroupService:
    """Service for Group model operations"""
    
    @staticmethod
    def create_group(
        creator: User,
        name: str,
        description: str,
        privacy: str = 'public',
        profile_picture: Optional[str] = None,
        cover_photo: Optional[str] = None,
        **extra_fields
    ) -> Group:
        """Create a new group"""
        # Validate privacy setting
        valid_privacy = [choice[0] for choice in GROUP_PRIVACY_CHOICES]
        if privacy not in valid_privacy:
            raise ValidationError(f"Privacy must be one of {valid_privacy}")
        
        # Validate group name uniqueness (optional: can be non-unique depending on requirements)
        if Group.objects.filter(name=name).exists():
            raise ValidationError(f"A group with name '{name}' already exists")
        
        try:
            with transaction.atomic():
                group = Group.objects.create(
                    creator=creator,
                    name=name,
                    description=description,
                    privacy=privacy,
                    profile_picture=profile_picture,
                    cover_photo=cover_photo,
                    **extra_fields
                )
                
                # Automatically add creator as admin
                from .group_member import GroupMemberService
                GroupMemberService.add_member(
                    group=group,
                    user=creator,
                    role='admin'
                )
                
                return group
        except IntegrityError as e:
            raise ValidationError(f"Failed to create group: {str(e)}")
    
    @staticmethod
    def get_group_by_id(group_id: int) -> Optional[Group]:
        """Retrieve group by ID"""
        try:
            return Group.objects.get(id=group_id)
        except Group.DoesNotExist:
            return None
    
    @staticmethod
    def get_group_by_name(name: str) -> Optional[Group]:
        """Retrieve group by name (exact match)"""
        try:
            return Group.objects.get(name=name)
        except Group.DoesNotExist:
            return None
    
    @staticmethod
    def update_group(group: Group, update_data: Dict[str, Any]) -> Group:
        """Update group information"""
        try:
            with transaction.atomic():
                for field, value in update_data.items():
                    if hasattr(group, field) and field not in ['id', 'creator', 'created_at']:
                        setattr(group, field, value)
                
                group.full_clean()
                group.save()
                return group
        except ValidationError as e:
            raise
    
    @staticmethod
    def delete_group(group: Group) -> bool:
        """Permanently delete a group"""
        try:
            group.delete()
            return True
        except Exception:
            return False
    
    @staticmethod
    def search_groups(
        query: str,
        privacy_filter: Optional[str] = None,
        creator: Optional[User] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Group]:
        """Search for groups by name or description"""
        queryset = Group.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
        
        if privacy_filter:
            queryset = queryset.filter(privacy=privacy_filter)
        
        if creator:
            queryset = queryset.filter(creator=creator)
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_groups_by_privacy(
        privacy: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Group]:
        """Get groups by privacy setting"""
        return list(Group.objects.filter(
            privacy=privacy
        ).order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_user_groups(
        user: User,
        include_private: bool = True,
        include_secret: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Group]:
        """Get groups that a user can see (based on privacy settings)"""
        from .group_member import GroupMemberService
        
        # Groups created by user
        created_groups = Group.objects.filter(creator=user)
        
        # Groups where user is a member
        member_groups_ids = GroupMemberService.get_user_groups(user).values_list('id', flat=True)
        member_groups = Group.objects.filter(id__in=member_groups_ids)
        
        # Public groups
        public_groups = Group.objects.filter(privacy='public')
        
        # Combine querysets
        queryset = (created_groups | member_groups | public_groups).distinct()
        
        if not include_private:
            queryset = queryset.exclude(privacy='private')
        
        if not include_secret:
            queryset = queryset.exclude(privacy='secret')
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_popular_groups(
        min_members: int = 10,
        days: int = 30,
        limit: int = 10
    ) -> List[Group]:
        """Get popular groups (most members, recently active)"""
        from django.db.models import Count
        
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        popular_groups = Group.objects.filter(
            member_count__gte=min_members,
            created_at__gte=time_threshold
        ).order_by('-member_count', '-created_at')[:limit]
        
        return list(popular_groups)
    
    @staticmethod
    def get_recommended_groups(
        user: User,
        limit: int = 10
    ) -> List[Group]:
        """Get group recommendations for a user"""
        from .group_member import GroupMemberService
        from users.services import UserFollowService
        
        # Get groups of people user follows
        following_users = UserFollowService.get_following(user)
        
        if following_users:
            # Get groups where followed users are members
            recommended_groups = Group.objects.filter(
                memberships__user__in=following_users,
                privacy='public'
            ).exclude(
                creator=user  # Exclude user's own groups
            ).distinct().order_by('-member_count')[:limit]
            
            return list(recommended_groups)
        
        # Fallback: popular public groups
        return GroupService.get_popular_groups(min_members=5, limit=limit)
    
    @staticmethod
    def update_member_count(group: Group) -> Group:
        """Update member count for a group"""
        from .group_member import GroupMemberService
        member_count = GroupMemberService.get_member_count(group)
        group.member_count = member_count
        group.save()
        return group
    
    @staticmethod
    def get_group_statistics(group: Group) -> Dict[str, Any]:
        """Get statistics for a group"""
        from .group_member import GroupMemberService
        
        members = GroupMemberService.get_group_members(group)
        admin_count = len([m for m in members if m.role == 'admin'])
        moderator_count = len([m for m in members if m.role == 'moderator'])
        member_count = len([m for m in members if m.role == 'member'])
        
        # Calculate activity (you might want to add activity tracking)
        # For now, we'll use member join rate
        recent_join_count = GroupMemberService.get_recent_joins(group, days=7)
        
        return {
            'total_members': group.member_count,
            'admin_count': admin_count,
            'moderator_count': moderator_count,
            'member_count': member_count,
            'recent_joins_7d': recent_join_count,
            'created_at': group.created_at,
            'privacy': group.privacy,
            'creator': group.creator.username
        }
    
    @staticmethod
    def change_privacy(group: Group, new_privacy: str) -> Group:
        """Change group privacy setting"""
        valid_privacy = [choice[0] for choice in Group.GROUP_PRIVACY_CHOICES]
        if new_privacy not in valid_privacy:
            raise ValidationError(f"Privacy must be one of {valid_privacy}")
        
        group.privacy = new_privacy
        group.save()
        return group
    
    @staticmethod
    def is_user_allowed_to_view(user: User, group: Group) -> bool:
        """Check if user is allowed to view group content"""
        from .group_member import GroupMemberService
        
        # Creator can always view
        if group.creator == user:
            return True
        
        # Public groups are viewable by anyone
        if group.privacy == 'public':
            return True
        
        # Private groups: only members can view
        if group.privacy == 'private':
            return GroupMemberService.is_member(group, user)
        
        # Secret groups: only members can view and they're hidden from searches
        if group.privacy == 'secret':
            return GroupMemberService.is_member(group, user)
        
        return False
    
    @staticmethod
    def is_user_allowed_to_join(user: User, group: Group) -> Tuple[bool, str]:
        """Check if user is allowed to join group, return (allowed, message)"""
        from .group_member import GroupMemberService
        
        # Already a member
        if GroupMemberService.is_member(group, user):
            return False, "Already a member"
        
        # Creator can always join (but they're automatically added)
        if group.creator == user:
            return True, ""
        
        # Public groups: anyone can join
        if group.privacy == 'public':
            return True, ""
        
        # Private groups: need invitation or approval
        if group.privacy == 'private':
            return False, "This group requires invitation or approval"
        
        # Secret groups: need invitation
        if group.privacy == 'secret':
            return False, "This group is secret and requires invitation"
        
        return False, "Cannot join this group"
    
    @staticmethod
    def get_group_activity_timeline(
        group: Group,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get group activity timeline (posts, events, etc.)"""
        # This is a placeholder - you'll need to integrate with your posts/events models
        # For now, we'll return member join timeline
        
        from .group_member import GroupMemberService
        recent_members = GroupMemberService.get_recent_joins_details(group, limit=limit)
        
        timeline = []
        for member in recent_members:
            timeline.append({
                'type': 'member_join',
                'user': member.user,
                'role': member.role,
                'timestamp': member.joined_at,
                'message': f"{member.user.username} joined as {member.role}"
            })
        
        return timeline
    
    @staticmethod
    def get_group_posts(group: Group, user: Optional[User] = None, limit=50, offset=0) -> List[Post]:
        # Check if user can view group posts
        if not GroupService.is_user_allowed_to_view(user, group):
            return []

        posts = Post.objects.filter(group=group, is_deleted=False)

        # Optionally filter by privacy within group
        # (e.g., if user is not member, only public group posts)

        return list(posts.order_by('-created_at')[offset:offset+limit])
    
    @staticmethod
    def cleanup_inactive_groups(days_inactive: int = 365, min_members: int = 0) -> List[Group]:
        """Find inactive groups (no activity for X days, few members)"""
        # This is a placeholder - you'll need to define what "inactive" means
        # For now, we'll return groups with few members
        inactive_groups = Group.objects.filter(
            member_count__lte=min_members
        ).order_by('member_count', 'created_at')
        
        return list(inactive_groups)
    