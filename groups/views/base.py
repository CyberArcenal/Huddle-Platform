from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from core.settings import logger
from global_utils.pagination import GroupsPagination
from groups.models.group import GROUP_PRIVACY_CHOICES, Group
from groups.serializers.base import (
    GroupSearchSerializer,
    GroupStatisticsSerializer,
    TransferOwnershipSerializer,
)
from groups.serializers.group import GroupCreateSerializer, GroupDisplaySerializer, GroupMinimalSerializer
from groups.serializers.member import (
    GroupMemberCreateSerializer,
    GroupMemberDisplaySerializer,
    GroupMemberMinimalSerializer,
    GroupMemberUpdateSerializer,
)
from groups.services.group import GroupService
from groups.services.group_member import GroupMemberService
from users.models import User
from rest_framework import serializers

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Input serializers for endpoints that previously used raw dicts
# ----------------------------------------------------------------------
class RemoveMemberInputSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(
        help_text="ID of the user to remove from the group"
    )


class ChangePrivacyInputSerializer(serializers.Serializer):
    privacy = serializers.ChoiceField(
        choices=GROUP_PRIVACY_CHOICES, help_text="New privacy setting"
    )


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_groups(paginator, page, request, serializer_class):
    """
    Construct a paginated data dict that matches the expected structure.
    """
    serializer = serializer_class(page, many=True, context={'request': request})
    data = {
        'page': paginator.page.number,
        'hasNext': paginator.page.has_next(),
        'hasPrev': paginator.page.has_previous(),
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class PaginatedGroupData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = GroupMinimalSerializer(many=True)


class GroupListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedGroupData()


class GroupCreateResponseData(serializers.Serializer):
    group = GroupDisplaySerializer()


class GroupCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupCreateResponseData()


class GroupDetailResponseData(serializers.Serializer):
    group = GroupDisplaySerializer()


class GroupDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupDetailResponseData()


class GroupUpdateResponseData(serializers.Serializer):
    group = GroupDisplaySerializer()


class GroupUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupUpdateResponseData()


class GroupDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class PaginatedGroupMemberData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = GroupMemberMinimalSerializer(many=True)


class GroupMembersListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedGroupMemberData()


class GroupMemberAddResponseData(serializers.Serializer):
    membership = GroupMemberDisplaySerializer()


class GroupMemberAddResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupMemberAddResponseData()


class GroupMemberRemoveResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class GroupMemberRoleUpdateResponseData(serializers.Serializer):
    membership = GroupMemberDisplaySerializer()


class GroupMemberRoleUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupMemberRoleUpdateResponseData()


class GroupJoinResponseData(serializers.Serializer):
    membership = GroupMemberDisplaySerializer()


class GroupJoinResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupJoinResponseData()


class GroupLeaveResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class GroupStatisticsResponseData(serializers.Serializer):
    statistics = GroupStatisticsSerializer()


class GroupStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupStatisticsResponseData()


class GroupTransferOwnershipResponseData(serializers.Serializer):
    detail = serializers.CharField()


class GroupTransferOwnershipResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupTransferOwnershipResponseData()


class GroupPrivacyResponseData(serializers.Serializer):
    group = GroupDisplaySerializer()


class GroupPrivacyResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupPrivacyResponseData()


class GroupPopularResponseData(serializers.Serializer):
    groups = GroupMinimalSerializer(many=True)


class GroupPopularResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GroupPopularResponseData()


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class MyGroupsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        parameters=[
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size", type=int, description="Results per page", required=False
            ),
            OpenApiParameter(
                name="include_private",
                type=bool,
                description="Include private groups (default: true)",
                required=False,
            ),
            OpenApiParameter(
                name="include_secret",
                type=bool,
                description="Include secret groups (default: false)",
                required=False,
            ),
        ],
        responses={200: GroupListResponseSerializer},
        description="List groups that the current user created or is a member of.",
    )
    def get(self, request):
        include_private = request.query_params.get("include_private", "true").lower() == "true"
        include_secret = request.query_params.get("include_secret", "false").lower() == "true"

        groups = GroupService.get_user_groups(
            user=request.user,
            include_private=include_private,
            include_secret=include_secret,
        )

        paginator = GroupsPagination()
        page = paginator.paginate_queryset(groups, request)
        paginated_data = wrap_paginated_groups(paginator, page, request, GroupMinimalSerializer)

        return Response(
            {
                "status": True,
                "message": "My groups retrieved.",
                "data": paginated_data,
            }
        )


class GroupListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        parameters=[
            OpenApiParameter(
                name="query",
                type=str,
                description="Search query for group name or description",
                required=False,
            ),
            OpenApiParameter(
                name="privacy",
                type=str,
                description="Filter by privacy (public, private, secret)",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: GroupListResponseSerializer},
        description="List groups: either user's groups, search results, or filtered by privacy.",
    )
    def get(self, request):
        serializer = GroupSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        if data.get("query"):
            groups = GroupService.search_groups(
                query=data["query"], privacy_filter=data.get("privacy")
            )
        elif data.get("privacy"):
            groups = GroupService.get_groups_by_privacy(privacy=data["privacy"])
        else:
            groups = GroupService.get_user_groups(user=request.user)

        paginator = GroupsPagination()
        page = paginator.paginate_queryset(groups, request)
        paginated_data = wrap_paginated_groups(paginator, page, request, GroupMinimalSerializer)

        return Response(
            {
                "status": True,
                "message": "Groups retrieved.",
                "data": paginated_data,
            }
        )

    @extend_schema(
        tags=["Group"],
        request=GroupCreateSerializer,
        responses={201: GroupCreateResponseSerializer},
        examples=[
            OpenApiExample(
                "Create public group",
                value={
                    "name": "Python Developers",
                    "description": "A group for Python enthusiasts",
                    "privacy": "public",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create private group",
                value={
                    "name": "Secret Project",
                    "description": "Invite only",
                    "privacy": "secret",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Group response",
                value={
                    "status": True,
                    "message": "Group created.",
                    "data": {
                        "group": {
                            "id": 1,
                            "name": "Python Developers",
                            "description": "A group for Python enthusiasts",
                            "creator": 5,
                            "privacy": "public",
                            "member_count": 0,
                            "created_at": "2025-03-07T12:34:56Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
        description="Create a new group. The current user becomes the creator and admin.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = GroupCreateSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        group = serializer.save()
        data = GroupDisplaySerializer(group, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Group created.",
                "data": {"group": data},
            },
            status=status.HTTP_201_CREATED,
        )


class GroupDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        responses={200: GroupDetailResponseSerializer},
        description="Retrieve details of a specific group.",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view this group",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        data = GroupDisplaySerializer(group, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Group retrieved.",
                "data": {"group": data},
            }
        )

    @extend_schema(
        tags=["Group"],
        request=GroupCreateSerializer,
        responses={200: GroupUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update group",
                value={"name": "New Group Name", "description": "Updated description"},
                request_only=True,
            )
        ],
        description="Update all fields of a group.",
    )
    @transaction.atomic
    def put(self, request, group_id):
        return self._update_group(request, group_id, partial=False)

    @extend_schema(
        tags=["Group"],
        request=GroupCreateSerializer,
        responses={200: GroupUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Partial update",
                value={"description": "Only update description"},
                request_only=True,
            )
        ],
        description="Partially update a group.",
    )
    def patch(self, request, group_id):
        return self._update_group(request, group_id, partial=True)

    def _update_group(self, request, group_id, partial=False):
        group = get_object_or_404(Group, id=group_id)
        if group.creator != request.user:
            membership = GroupMemberService.get_membership(group, request.user)
            if not membership or membership.role != "admin":
                return Response(
                    {
                        "status": False,
                        "message": "Only admins can update group details",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        serializer = GroupCreateSerializer(
            group, data=request.data, partial=partial, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            updated_group = GroupService.update_group(group, serializer.validated_data)
        except Exception as e:
            logger.debug(e)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = GroupDisplaySerializer(updated_group, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Group updated.",
                "data": {"group": data},
            }
        )

    @extend_schema(
        tags=["Group"],
        responses={204: GroupDeleteResponseSerializer},
        description="Delete a group. Only the creator can delete.",
    )
    @transaction.atomic
    def delete(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if group.creator != request.user:
            return Response(
                {
                    "status": False,
                    "message": "Only the group creator can delete the group",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        success = GroupService.delete_group(group)
        if success:
            return Response(
                {
                    "status": True,
                    "message": "Group deleted.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        return Response(
            {
                "status": False,
                "message": "Failed to delete group",
                "data": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class GroupMembersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        parameters=[
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: GroupMembersListResponseSerializer},
        description="List all members of a group (paginated).",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view members",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        members = GroupMemberService.get_group_members(group)
        paginator = GroupsPagination()
        page = paginator.paginate_queryset(members, request)
        paginated_data = wrap_paginated_groups(paginator, page, request, GroupMemberMinimalSerializer)
        return Response(
            {
                "status": True,
                "message": "Members retrieved.",
                "data": paginated_data,
            }
        )

    @extend_schema(
        tags=["Group"],
        request=GroupMemberCreateSerializer,
        responses={201: GroupMemberAddResponseSerializer},
        examples=[
            OpenApiExample(
                "Add member", value={"user_id": 42, "role": "member"}, request_only=True
            ),
            OpenApiExample(
                "Member response",
                value={
                    "status": True,
                    "message": "Member added.",
                    "data": {
                        "membership": {
                            "id": 1,
                            "group": 1,
                            "user": 42,
                            "role": "member",
                            "joined_at": "2025-03-07T12:34:56Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
        description="Add a user to the group. Requires admin permissions.",
    )
    @transaction.atomic
    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        serializer = GroupMemberCreateSerializer(
            data=request.data, context={"group": group, "request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        success, membership = GroupMemberService.add_member(
            group=group, user=data["user"], role=data["role"]
        )
        if success:
            membership_data = GroupMemberDisplaySerializer(membership).data
            return Response(
                {
                    "status": True,
                    "message": "Member added.",
                    "data": {"membership": membership_data},
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {
                "status": False,
                "message": "User is already a member",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        tags=["Group"],
        request=RemoveMemberInputSerializer,
        responses={204: GroupMemberRemoveResponseSerializer},
        examples=[
            OpenApiExample("Remove member", value={"user_id": 42}, request_only=True)
        ],
        description="Remove a user from the group. Requires appropriate permissions.",
    )
    @transaction.atomic
    def delete(self, request, group_id, user_id):
        group = get_object_or_404(Group, id=group_id)
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "User does not exist",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Permission checks
        if request.user != user and group.creator != request.user:
            requester_membership = GroupMemberService.get_membership(
                group, request.user
            )
            if not requester_membership or requester_membership.role != "admin":
                return Response(
                    {
                        "status": False,
                        "message": "Only admins can remove other members",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            target_membership = GroupMemberService.get_membership(group, user)
            if target_membership and target_membership.role == "admin":
                return Response(
                    {
                        "status": False,
                        "message": "Admins cannot remove other admins",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        success = GroupMemberService.remove_member(group, user)
        if success:
            return Response(
                {
                    "status": True,
                    "message": "Member removed.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        return Response(
            {
                "status": False,
                "message": "Failed to remove member",
                "data": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class GroupMemberRoleView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        request=GroupMemberUpdateSerializer,
        responses={200: GroupMemberRoleUpdateResponseSerializer},
        examples=[
            OpenApiExample("Update role", value={"role": "admin"}, request_only=True)
        ],
        description="Update a member's role (admin, moderator, member). Requires appropriate permissions.",
    )
    def patch(self, request, group_id, user_id):
        group = get_object_or_404(Group, id=group_id)
        target_user = get_object_or_404(User, id=user_id)
        serializer = GroupMemberUpdateSerializer(
            data=request.data,
            context={"group": group, "target_user": target_user, "request": request},
        )
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            membership = GroupMemberService.update_member_role(
                group=group,
                user=target_user,
                new_role=serializer.validated_data["role"],
                changed_by=request.user,
            )
        except Exception as e:
            logger.debug(e)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = GroupMemberDisplaySerializer(membership).data
        return Response(
            {
                "status": True,
                "message": "Member role updated.",
                "data": {"membership": data},
            }
        )


class GroupJoinView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        responses={201: GroupJoinResponseSerializer},
        description="Join a public group. For private groups, the user must be invited.",
    )
    @transaction.atomic
    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        allowed, message = GroupService.is_user_allowed_to_join(request.user, group)
        if not allowed:
            return Response(
                {
                    "status": False,
                    "message": message,
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        success, membership = GroupMemberService.add_member(
            group=group, user=request.user, role="member"
        )
        if success:
            data = GroupMemberDisplaySerializer(membership).data
            return Response(
                {
                    "status": True,
                    "message": "Joined group.",
                    "data": {"membership": data},
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {
                "status": False,
                "message": "Already a member" if membership else "Failed to join",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class GroupLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        responses={204: GroupLeaveResponseSerializer},
        description="Leave a group. Creator cannot leave without transferring ownership first.",
    )
    @transaction.atomic
    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupMemberService.is_member(group, request.user):
            return Response(
                {
                    "status": False,
                    "message": "You are not a member of this group",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if group.creator == request.user:
            return Response(
                {
                    "status": False,
                    "message": "Group creator cannot leave. Transfer ownership first.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        success = GroupMemberService.remove_member(group, request.user)
        if success:
            return Response(
                {
                    "status": True,
                    "message": "Left group.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        return Response(
            {
                "status": False,
                "message": "Failed to leave group",
                "data": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class GroupStatisticsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        responses={200: GroupStatisticsResponseSerializer},
        description="Get statistics for a group (member count, posts count, etc.).",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view statistics",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        stats = GroupService.get_group_statistics(group)
        return Response(
            {
                "status": True,
                "message": "Group statistics retrieved.",
                "data": {"statistics": stats},
            }
        )


class GroupTransferOwnershipView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        request=TransferOwnershipSerializer,
        responses={200: GroupTransferOwnershipResponseSerializer},
        examples=[
            OpenApiExample(
                "Transfer request", value={"new_owner_id": 42}, request_only=True
            ),
            OpenApiExample(
                "Transfer response",
                value={
                    "status": True,
                    "message": "Ownership transferred.",
                    "data": {"detail": "Ownership transferred successfully."},
                },
                response_only=True,
            ),
        ],
        description="Transfer group ownership to another member. Only current creator can do this.",
    )
    @transaction.atomic
    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if group.creator != request.user:
            return Response(
                {
                    "status": False,
                    "message": "Only the group creator can transfer ownership",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = TransferOwnershipSerializer(
            data=request.data, context={"group": group, "current_owner": request.user}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        success, message = GroupMemberService.transfer_ownership(
            group=group, current_owner=request.user, new_owner=data["new_owner"]
        )
        if success:
            return Response(
                {
                    "status": True,
                    "message": message,
                    "data": {"detail": message},
                }
            )
        return Response(
            {
                "status": False,
                "message": message,
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class GroupPrivacyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        request=ChangePrivacyInputSerializer,
        responses={200: GroupPrivacyResponseSerializer},
        examples=[
            OpenApiExample(
                "Change privacy", value={"privacy": "secret"}, request_only=True
            )
        ],
        description="Change group privacy (public, private, secret). Only creator can do this.",
    )
    def patch(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if group.creator != request.user:
            return Response(
                {
                    "status": False,
                    "message": "Only the group creator can change privacy",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ChangePrivacyInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_privacy = serializer.validated_data["privacy"]
        try:
            updated_group = GroupService.change_privacy(group, new_privacy)
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = GroupDisplaySerializer(updated_group, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Group privacy updated.",
                "data": {"group": data},
            }
        )


class GroupPopularView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        parameters=[
            OpenApiParameter(
                name="limit", type=int, description="Number of results", required=False
            ),
            OpenApiParameter(
                name="min_members",
                type=int,
                description="Minimum member count",
                required=False,
            ),
            OpenApiParameter(
                name="days",
                type=int,
                description="Lookback period for activity",
                required=False,
            ),
        ],
        responses={200: GroupPopularResponseSerializer},
        description="Get popular groups based on recent activity and member count.",
    )
    def get(self, request):
        limit = int(request.query_params.get("limit", 10))
        min_members = int(request.query_params.get("min_members", 10))
        days = int(request.query_params.get("days", 30))
        popular_groups = GroupService.get_popular_groups(
            min_members=min_members, days=days, limit=limit
        )
        data = GroupMinimalSerializer(
            popular_groups, many=True, context={"request": request}
        ).data
        return Response(
            {
                "status": True,
                "message": "Popular groups retrieved.",
                "data": {"groups": data},
            }
        )


class GroupSearchMembersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Group"],
        parameters=[
            OpenApiParameter(
                name="query",
                type=str,
                description="Search query for username or name",
                required=True,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: GroupMembersListResponseSerializer},
        description="Search members within a group by username or name.",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view members",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        query = request.query_params.get("query", "")
        if not query:
            return Response(
                {
                    "status": False,
                    "message": "query parameter is required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        members = GroupMemberService.search_members(group=group, query=query)
        paginator = GroupsPagination()
        page = paginator.paginate_queryset(members, request)
        paginated_data = wrap_paginated_groups(paginator, page, request, GroupMemberMinimalSerializer)
        return Response(
            {
                "status": True,
                "message": "Search results.",
                "data": paginated_data,
            }
        )