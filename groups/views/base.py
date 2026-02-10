from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q

from groups.models.base import Group
from groups.serializers.base import GroupCreateSerializer, GroupMemberCreateSerializer, GroupMemberSerializer, GroupMemberUpdateSerializer, GroupSearchSerializer, GroupSerializer, GroupStatisticsSerializer, GroupUpdateSerializer, TransferOwnershipSerializer
from groups.services.group import GroupService
from groups.services.group_member import GroupMemberService
from users.models.base import User



class GroupListView(APIView):
    """View for listing and creating groups"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """List groups with filtering and search"""
        serializer = GroupSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = serializer.validated_data
        
        if data.get('query'):
            # Search groups
            groups = GroupService.search_groups(
                query=data['query'],
                privacy_filter=data.get('privacy'),
                limit=data['limit'],
                offset=data['offset']
            )
        elif data.get('privacy'):
            # Filter by privacy
            groups = GroupService.get_groups_by_privacy(
                privacy=data['privacy'],
                limit=data['limit'],
                offset=data['offset']
            )
        else:
            # Get user's groups
            groups = GroupService.get_user_groups(
                user=request.user,
                limit=data['limit'],
                offset=data['offset']
            )
        
        # Serialize response
        group_serializer = GroupSerializer(
            groups,
            many=True,
            context={'request': request}
        )
        
        return Response({
            'count': len(groups),
            'results': group_serializer.data
        })
    
    def post(self, request):
        """Create a new group"""
        serializer = GroupCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        group = serializer.save()
        
        return Response(
            GroupSerializer(group, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class GroupDetailView(APIView):
    """View for retrieving, updating, and deleting groups"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, group_id):
        """Retrieve group details"""
        group = get_object_or_404(Group, id=group_id)
        
        # Check if user can view group
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {'detail': 'You do not have permission to view this group'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = GroupSerializer(group, context={'request': request})
        return Response(serializer.data)
    
    def put(self, request, group_id):
        """Update group (full update)"""
        return self._update_group(request, group_id, partial=False)
    
    def patch(self, request, group_id):
        """Update group (partial update)"""
        return self._update_group(request, group_id, partial=True)
    
    def _update_group(self, request, group_id, partial=False):
        """Helper method for updating groups"""
        group = get_object_or_404(Group, id=group_id)
        
        # Check permissions
        if group.creator != request.user:
            membership = GroupMemberService.get_membership(group, request.user)
            if not membership or membership.role != 'admin':
                return Response(
                    {'detail': 'Only admins can update group details'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        serializer = GroupUpdateSerializer(
            group,
            data=request.data,
            partial=partial,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use GroupService to update
        try:
            updated_group = GroupService.update_group(
                group,
                serializer.validated_data
            )
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            GroupSerializer(updated_group, context={'request': request}).data
        )
    
    def delete(self, request, group_id):
        """Delete a group"""
        group = get_object_or_404(Group, id=group_id)
        
        # Only creator can delete
        if group.creator != request.user:
            return Response(
                {'detail': 'Only the group creator can delete the group'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        success = GroupService.delete_group(group)
        
        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                {'detail': 'Failed to delete group'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GroupMembersView(APIView):
    """View for managing group members"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, group_id):
        """List group members"""
        group = get_object_or_404(Group, id=group_id)
        
        # Check if user can view members
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {'detail': 'You do not have permission to view members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get members
        members = GroupMemberService.get_group_members(
            group,
            limit=request.query_params.get('limit', 100),
            offset=request.query_params.get('offset', 0)
        )
        
        serializer = GroupMemberSerializer(members, many=True)
        return Response(serializer.data)
    
    def post(self, request, group_id):
        """Add a member to group"""
        group = get_object_or_404(Group, id=group_id)
        
        serializer = GroupMemberCreateSerializer(
            data=request.data,
            context={'group': group, 'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = serializer.validated_data
        
        # Add member using service
        success, membership = GroupMemberService.add_member(
            group=group,
            user=data['user'],
            role=data['role']
        )
        
        if success:
            return Response(
                GroupMemberSerializer(membership).data,
                status=status.HTTP_201_CREATED
            )
        else:
            return Response(
                {'detail': 'User is already a member'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def delete(self, request, group_id):
        """Remove a member from group"""
        group = get_object_or_404(Group, id=group_id)
        
        user_id = request.data.get('user_id')
        if not user_id:
            return Response(
                {'detail': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'detail': 'User does not exist'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        # Creator can remove anyone
        # Admins can remove non-admins
        # Users can remove themselves
        
        if request.user != user and group.creator != request.user:
            # Check if requester is admin
            requester_membership = GroupMemberService.get_membership(group, request.user)
            if not requester_membership or requester_membership.role != 'admin':
                return Response(
                    {'detail': 'Only admins can remove other members'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if target is admin (admins can't remove other admins)
            target_membership = GroupMemberService.get_membership(group, user)
            if target_membership and target_membership.role == 'admin':
                return Response(
                    {'detail': 'Admins cannot remove other admins'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Remove member
        success = GroupMemberService.remove_member(group, user)
        
        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                {'detail': 'Failed to remove member'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GroupMemberRoleView(APIView):
    """View for updating member roles"""
    permission_classes = [IsAuthenticated]
    
    def patch(self, request, group_id, user_id):
        """Update member role"""
        group = get_object_or_404(Group, id=group_id)
        target_user = get_object_or_404(User, id=user_id)
        
        serializer = GroupMemberUpdateSerializer(
            data=request.data,
            context={
                'group': group,
                'target_user': target_user,
                'request': request
            }
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update role using service
        try:
            membership = GroupMemberService.update_member_role(
                group=group,
                user=target_user,
                new_role=serializer.validated_data['role'],
                changed_by=request.user
            )
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(GroupMemberSerializer(membership).data)


class GroupJoinView(APIView):
    """View for joining groups"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, group_id):
        """Join a group"""
        group = get_object_or_404(Group, id=group_id)
        
        # Check if user can join
        allowed, message = GroupService.is_user_allowed_to_join(request.user, group)
        
        if not allowed:
            return Response(
                {'detail': message},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Add member
        success, membership = GroupMemberService.add_member(
            group=group,
            user=request.user,
            role='member'
        )
        
        if success:
            return Response(
                GroupMemberSerializer(membership).data,
                status=status.HTTP_201_CREATED
            )
        else:
            return Response(
                {'detail': 'Already a member' if membership else 'Failed to join'},
                status=status.HTTP_400_BAD_REQUEST
            )


class GroupLeaveView(APIView):
    """View for leaving groups"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, group_id):
        """Leave a group"""
        group = get_object_or_404(Group, id=group_id)
        
        # Check if user is member
        if not GroupMemberService.is_member(group, request.user):
            return Response(
                {'detail': 'You are not a member of this group'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Creator cannot leave (must transfer ownership first)
        if group.creator == request.user:
            return Response(
                {'detail': 'Group creator cannot leave. Transfer ownership first.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Remove member
        success = GroupMemberService.remove_member(group, request.user)
        
        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                {'detail': 'Failed to leave group'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GroupStatisticsView(APIView):
    """View for group statistics"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, group_id):
        """Get group statistics"""
        group = get_object_or_404(Group, id=group_id)
        
        # Check if user can view statistics
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {'detail': 'You do not have permission to view statistics'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get statistics
        stats = GroupService.get_group_statistics(group)
        
        serializer = GroupStatisticsSerializer(stats)
        return Response(serializer.data)


class GroupTransferOwnershipView(APIView):
    """View for transferring group ownership"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, group_id):
        """Transfer group ownership"""
        group = get_object_or_404(Group, id=group_id)
        
        # Check if user is creator
        if group.creator != request.user:
            return Response(
                {'detail': 'Only the group creator can transfer ownership'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = TransferOwnershipSerializer(
            data=request.data,
            context={'group': group, 'current_owner': request.user}
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = serializer.validated_data
        
        # Transfer ownership using service
        success, message = GroupMemberService.transfer_ownership(
            group=group,
            current_owner=request.user,
            new_owner=data['new_owner']
        )
        
        if success:
            return Response({'detail': message})
        else:
            return Response(
                {'detail': message},
                status=status.HTTP_400_BAD_REQUEST
            )


class GroupPrivacyView(APIView):
    """View for changing group privacy"""
    permission_classes = [IsAuthenticated]
    
    def patch(self, request, group_id):
        """Change group privacy"""
        group = get_object_or_404(Group, id=group_id)
        
        # Check if user is creator
        if group.creator != request.user:
            return Response(
                {'detail': 'Only the group creator can change privacy'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        new_privacy = request.data.get('privacy')
        if not new_privacy:
            return Response(
                {'detail': 'privacy field is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            updated_group = GroupService.change_privacy(group, new_privacy)
            return Response(
                GroupSerializer(updated_group, context={'request': request}).data
            )
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class GroupRecommendationsView(APIView):
    """View for group recommendations"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get group recommendations for current user"""
        limit = int(request.query_params.get('limit', 10))
        
        recommendations = GroupService.get_recommended_groups(
            user=request.user,
            limit=limit
        )
        
        serializer = GroupSerializer(
            recommendations,
            many=True,
            context={'request': request}
        )
        
        return Response(serializer.data)


class GroupPopularView(APIView):
    """View for popular groups"""
    def get(self, request):
        """Get popular groups"""
        limit = int(request.query_params.get('limit', 10))
        min_members = int(request.query_params.get('min_members', 10))
        days = int(request.query_params.get('days', 30))
        
        popular_groups = GroupService.get_popular_groups(
            min_members=min_members,
            days=days,
            limit=limit
        )
        
        serializer = GroupSerializer(
            popular_groups,
            many=True,
            context={'request': request}
        )
        
        return Response(serializer.data)


class GroupSearchMembersView(APIView):
    """View for searching members within a group"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, group_id):
        """Search members in group"""
        group = get_object_or_404(Group, id=group_id)
        
        # Check if user can view members
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {'detail': 'You do not have permission to view members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        query = request.query_params.get('query', '')
        limit = int(request.query_params.get('limit', 20))
        
        if not query:
            return Response(
                {'detail': 'query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        members = GroupMemberService.search_members(
            group=group,
            query=query,
            limit=limit
        )
        
        serializer = GroupMemberSerializer(members, many=True)
        return Response(serializer.data)