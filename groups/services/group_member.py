from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from typing import Optional, List, Dict, Any, Tuple

from users.models.user import User
from ..models import Group, GroupMember


class GroupMemberService:
    """Service for GroupMember model operations"""

    @staticmethod
    def add_member(
        group: Group,
        user: User,
        role: str = "member",
        invited_by: Optional[User] = None,
    ) -> Tuple[bool, Optional[GroupMember]]:
        """Add a user to a group"""
        # Validate role
        valid_roles = [choice[0] for choice in GroupMember.ROLE_CHOICES]
        if role not in valid_roles:
            raise ValidationError(f"Role must be one of {valid_roles}")

        # Check if already a member
        if GroupMemberService.is_member(group, user):
            return False, GroupMemberService.get_membership(group, user)

        try:
            with transaction.atomic():
                membership = GroupMember.objects.create(
                    group=group, user=user, role=role
                )

                # Update group member count
                from .group import GroupService

                GroupService.update_member_count(group)

                return True, membership
        except IntegrityError:
            # Race condition: member was added concurrently
            return False, GroupMemberService.get_membership(group, user)

    @staticmethod
    def remove_member(group: Group, user: User) -> bool:
        """Remove a user from a group"""
        # Creator cannot be removed (or can be with special handling)
        if group.creator == user:
            # Option 1: Prevent removal
            # raise ValidationError("Group creator cannot be removed")
            # Option 2: Allow but handle differently
            pass

        try:
            deleted_count, _ = GroupMember.objects.filter(
                group=group, user=user
            ).delete()

            if deleted_count > 0:
                # Update group member count
                from .group import GroupService

                GroupService.update_member_count(group)

                return True
            return False
        except Exception:
            return False

    @staticmethod
    def update_member_role(
        group: Group, user: User, new_role: str, changed_by: User
    ) -> Optional[GroupMember]:
        """Update a member's role"""
        # Validate role
        valid_roles = [choice[0] for choice in GroupMember.ROLE_CHOICES]
        if new_role not in valid_roles:
            raise ValidationError(f"Role must be one of {valid_roles}")

        # Check permissions (implement based on your requirements)
        # For example, only admins can promote to admin, etc.

        membership = GroupMemberService.get_membership(group, user)
        if not membership:
            raise ValidationError("User is not a member of this group")

        # Prevent changing creator's role (optional)
        if group.creator == user:
            raise ValidationError("Cannot change group creator's role")

        membership.role = new_role
        membership.save()

        return membership

    @staticmethod
    def is_member(group: Group, user: User) -> bool:
        """Check if user is a member of group"""
        return GroupMember.objects.filter(group=group, user=user).exists()

    @staticmethod
    def get_membership(group: Group, user: User) -> Optional[GroupMember]:
        """Get membership details for a user in a group"""
        try:
            return GroupMember.objects.get(group=group, user=user)
        except GroupMember.DoesNotExist:
            return None

    @staticmethod
    def get_group_members(
        group: Group, role: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[GroupMember]:
        """Get all members of a group"""
        queryset = GroupMember.objects.filter(group=group).select_related("user")

        if role:
            queryset = queryset.filter(role=role)

        return list(queryset.order_by("joined_at")[offset : offset + limit])

    @staticmethod
    def get_user_groups(
        user: User, role: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[Group]:
        """Get all groups that a user belongs to"""
        queryset = Group.objects.filter(memberships__user=user)

        if role:
            queryset = queryset.filter(memberships__role=role)

        return list(
            queryset.order_by("-memberships__joined_at")[offset : offset + limit]
        )

    @staticmethod
    def get_member_count(group: Group) -> int:
        """Get total number of members in a group"""
        return GroupMember.objects.filter(group=group).count()

    @staticmethod
    def get_role_count(group: Group, role: str) -> int:
        """Get count of members with specific role"""
        return GroupMember.objects.filter(group=group, role=role).count()

    @staticmethod
    def get_recent_joins(group: Group, days: int = 7) -> int:
        """Count recent member joins"""
        time_threshold = timezone.now() - timezone.timedelta(days=days)

        return GroupMember.objects.filter(
            group=group, joined_at__gte=time_threshold
        ).count()

    @staticmethod
    def get_recent_joins_details(group: Group, limit: int = 20) -> List[GroupMember]:
        """Get details of recent member joins"""
        return list(
            GroupMember.objects.filter(group=group)
            .select_related("user")
            .order_by("-joined_at")[:limit]
        )

    @staticmethod
    def search_members(group: Group, query: str, limit: int = 20) -> List[GroupMember]:
        """Search members within a group by username or email"""
        from django.db.models import Q

        members = (
            GroupMember.objects.filter(group=group)
            .filter(
                Q(user__username__icontains=query)
                | Q(user__email__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
            )
            .select_related("user")[:limit]
        )

        return list(members)

    @staticmethod
    def transfer_ownership(
        group: Group, current_owner: User, new_owner: User
    ) -> Tuple[bool, str]:
        """Transfer group ownership to another member"""
        # Verify current owner
        if group.creator != current_owner:
            return False, "Only the current owner can transfer ownership"

        # Verify new owner is a member
        if not GroupMemberService.is_member(group, new_owner):
            return False, "New owner must be a member of the group"

        try:
            with transaction.atomic():
                # Update group creator
                group.creator = new_owner
                group.save()

                # Update roles
                # Demote current owner to admin
                current_membership = GroupMemberService.get_membership(
                    group, current_owner
                )
                if current_membership:
                    current_membership.role = "admin"
                    current_membership.save()

                # Promote new owner to admin (if not already)
                new_membership = GroupMemberService.get_membership(group, new_owner)
                if new_membership:
                    new_membership.role = "admin"
                    new_membership.save()

                return True, "Ownership transferred successfully"
        except Exception as e:
            logger.debug(e)
            return False, f"Failed to transfer ownership: {str(e)}"

    @staticmethod
    def get_member_hierarchy(group: Group) -> Dict[str, List[Dict[str, Any]]]:
        """Get group member hierarchy by role"""
        members_by_role = {}

        for role_choice in GroupMember.ROLE_CHOICES:
            role = role_choice[0]
            members = (
                GroupMember.objects.filter(group=group, role=role)
                .select_related("user")
                .order_by("joined_at")
            )

            members_by_role[role] = [
                {
                    "user": member.user,
                    "joined_at": member.joined_at,
                    "is_creator": group.creator == member.user,
                }
                for member in members
            ]

        return members_by_role

    @staticmethod
    def get_member_activity(group: Group, user: User, days: int = 30) -> Dict[str, Any]:
        """Get member activity statistics"""
        # This is a placeholder - you'll need to integrate with your activity tracking
        # For now, we'll return basic membership info

        membership = GroupMemberService.get_membership(group, user)
        if not membership:
            raise ValidationError("User is not a member of this group")

        return {
            "role": membership.role,
            "joined_at": membership.joined_at,
            "days_as_member": (timezone.now() - membership.joined_at).days,
            "is_creator": group.creator == user,
        }

    @staticmethod
    def kick_inactive_members(
        group: Group, inactive_days: int = 90, exempt_roles: List[str] = ["admin"]
    ) -> List[User]:
        """Kick members who have been inactive for specified days"""
        # This is a placeholder - you'll need to define "inactivity"
        # For now, we'll just return empty list
        # Implementation depends on your activity tracking system

        return []
