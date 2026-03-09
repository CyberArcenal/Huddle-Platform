from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from global_utils.pagination import GroupsPagination
from groups.models.base import Group
from groups.serializers.base import (
    GroupCreateSerializer,
    GroupMemberCreateSerializer,
    GroupMemberSerializer,
    GroupMemberUpdateSerializer,
    GroupSearchSerializer,
    GroupSerializer,
    GroupStatisticsSerializer,
    GroupUpdateSerializer,
    TransferOwnershipSerializer,
)
from groups.services.group import GroupService
from groups.services.group_member import GroupMemberService
from users.models.base import User
from rest_framework import serializers
from groups.serializers.base import GroupSerializer, GroupMemberSerializer


# ----- New input serializers for endpoints that previously used raw dicts -----
class RemoveMemberInputSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(
        help_text="ID of the user to remove from the group"
    )


class ChangePrivacyInputSerializer(serializers.Serializer):
    privacy = serializers.ChoiceField(
        choices=Group.PRIVACY_CHOICES, help_text="New privacy setting"
    )


# -----------------------------------------------------------------------------


# ----- Paginated response serializers for drf-spectacular -----
class PaginatedGroupSerializer(serializers.Serializer):
    """Matches the custom pagination response from GroupsPagination"""

    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = GroupSerializer(many=True)


class PaginatedGroupMemberSerializer(serializers.Serializer):
    """Matches the custom pagination response from GroupsPagination"""

    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = GroupMemberSerializer(many=True)


# --------------------------------------------------------------


class GroupListView(APIView):
    """View for listing and creating groups"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
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
        responses={200: PaginatedGroupSerializer},
        description="List groups: either user's groups, search results, or filtered by privacy.",
    )
    def get(self, request):
        """List groups with filtering and search"""
        serializer = GroupSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Get full queryset from services (no slicing)
        if data.get("query"):
            groups = GroupService.search_groups(
                query=data["query"], privacy_filter=data.get("privacy")
            )
        elif data.get("privacy"):
            groups = GroupService.get_groups_by_privacy(privacy=data["privacy"])
        else:
            groups = GroupService.get_user_groups(user=request.user)

        # Apply pagination
        paginator = GroupsPagination()
        page = paginator.paginate_queryset(groups, request)
        group_serializer = GroupSerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(group_serializer.data)

    @extend_schema(
        request=GroupCreateSerializer,
        responses={201: GroupSerializer},
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
                    "privacy": "private",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Group response",
                value={
                    "id": 1,
                    "name": "Python Developers",
                    "description": "A group for Python enthusiasts",
                    "creator": 5,
                    "privacy": "public",
                    "member_count": 0,
                    "created_at": "2025-03-07T12:34:56Z",
                },
                response_only=True,
            ),
        ],
        description="Create a new group. The current user becomes the creator and admin.",
    )
    @transaction.atomic
    def post(self, request):
        """Create a new group"""
        serializer = GroupCreateSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        group = serializer.save()
        return Response(
            GroupSerializer(group, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class GroupDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: GroupSerializer},
        description="Retrieve details of a specific group.",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {"detail": "You do not have permission to view this group"},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = GroupSerializer(group, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=GroupUpdateSerializer,
        responses={200: GroupSerializer},
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
        request=GroupUpdateSerializer,
        responses={200: GroupSerializer},
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
                    {"detail": "Only admins can update group details"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        serializer = GroupUpdateSerializer(
            group, data=request.data, partial=partial, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            updated_group = GroupService.update_group(group, serializer.validated_data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            GroupSerializer(updated_group, context={"request": request}).data
        )

    @extend_schema(
        responses={204: None},
        description="Delete a group. Only the creator can delete.",
    )
    @transaction.atomic
    def delete(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if group.creator != request.user:
            return Response(
                {"detail": "Only the group creator can delete the group"},
                status=status.HTTP_403_FORBIDDEN,
            )
        success = GroupService.delete_group(group)
        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {"detail": "Failed to delete group"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class GroupMembersView(APIView):
    """View for managing group members"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
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
        responses={200: PaginatedGroupMemberSerializer},
        description="List all members of a group (paginated).",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {"detail": "You do not have permission to view members"},
                status=status.HTTP_403_FORBIDDEN,
            )
        members = GroupMemberService.get_group_members(group)
        paginator = GroupsPagination()
        page = paginator.paginate_queryset(members, request)
        serializer = GroupMemberSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=GroupMemberCreateSerializer,
        responses={201: GroupMemberSerializer},
        examples=[
            OpenApiExample(
                "Add member", value={"user_id": 42, "role": "member"}, request_only=True
            ),
            OpenApiExample(
                "Member response",
                value={
                    "id": 1,
                    "group": 1,
                    "user": 42,
                    "role": "member",
                    "joined_at": "2025-03-07T12:34:56Z",
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
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        success, membership = GroupMemberService.add_member(
            group=group, user=data["user"], role=data["role"]
        )
        if success:
            return Response(
                GroupMemberSerializer(membership).data, status=status.HTTP_201_CREATED
            )
        return Response(
            {"detail": "User is already a member"}, status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        request=RemoveMemberInputSerializer,  # ✅ Now using proper serializer
        responses={204: None},
        examples=[
            OpenApiExample("Remove member", value={"user_id": 42}, request_only=True)
        ],
        description="Remove a user from the group. Requires appropriate permissions.",
    )
    @transaction.atomic
    def delete(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        serializer = RemoveMemberInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_id = serializer.validated_data["user_id"]
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "User does not exist"}, status=status.HTTP_404_NOT_FOUND
            )

        # Permission checks (unchanged)
        if request.user != user and group.creator != request.user:
            requester_membership = GroupMemberService.get_membership(
                group, request.user
            )
            if not requester_membership or requester_membership.role != "admin":
                return Response(
                    {"detail": "Only admins can remove other members"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            target_membership = GroupMemberService.get_membership(group, user)
            if target_membership and target_membership.role == "admin":
                return Response(
                    {"detail": "Admins cannot remove other admins"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        success = GroupMemberService.remove_member(group, user)
        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {"detail": "Failed to remove member"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class GroupMemberRoleView(APIView):
    """View for updating member roles"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=GroupMemberUpdateSerializer,
        responses={200: GroupMemberSerializer},
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
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            membership = GroupMemberService.update_member_role(
                group=group,
                user=target_user,
                new_role=serializer.validated_data["role"],
                changed_by=request.user,
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(GroupMemberSerializer(membership).data)


class GroupJoinView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={201: GroupMemberSerializer},
        description="Join a public group. For private groups, the user must be invited.",
    )
    @transaction.atomic
    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        allowed, message = GroupService.is_user_allowed_to_join(request.user, group)
        if not allowed:
            return Response({"detail": message}, status=status.HTTP_403_FORBIDDEN)
        success, membership = GroupMemberService.add_member(
            group=group, user=request.user, role="member"
        )
        if success:
            return Response(
                GroupMemberSerializer(membership).data, status=status.HTTP_201_CREATED
            )
        return Response(
            {"detail": "Already a member" if membership else "Failed to join"},
            status=status.HTTP_400_BAD_REQUEST,
        )


class GroupLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={204: None},
        description="Leave a group. Creator cannot leave without transferring ownership first.",
    )
    @transaction.atomic
    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupMemberService.is_member(group, request.user):
            return Response(
                {"detail": "You are not a member of this group"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if group.creator == request.user:
            return Response(
                {"detail": "Group creator cannot leave. Transfer ownership first."},
                status=status.HTTP_403_FORBIDDEN,
            )
        success = GroupMemberService.remove_member(group, request.user)
        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {"detail": "Failed to leave group"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class GroupStatisticsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: GroupStatisticsSerializer},
        description="Get statistics for a group (member count, posts count, etc.).",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {"detail": "You do not have permission to view statistics"},
                status=status.HTTP_403_FORBIDDEN,
            )
        stats = GroupService.get_group_statistics(group)
        serializer = GroupStatisticsSerializer(stats)
        return Response(serializer.data)


class GroupTransferOwnershipView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=TransferOwnershipSerializer,
        responses={
            200: {"type": "object", "properties": {"detail": {"type": "string"}}}
        },
        examples=[
            OpenApiExample(
                "Transfer request", value={"new_owner_id": 42}, request_only=True
            ),
            OpenApiExample(
                "Transfer response",
                value={"detail": "Ownership transferred successfully."},
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
                {"detail": "Only the group creator can transfer ownership"},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = TransferOwnershipSerializer(
            data=request.data, context={"group": group, "current_owner": request.user}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        success, message = GroupMemberService.transfer_ownership(
            group=group, current_owner=request.user, new_owner=data["new_owner"]
        )
        if success:
            return Response({"detail": message})
        return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)


class GroupPrivacyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChangePrivacyInputSerializer,  # ✅ Now using proper serializer
        responses={200: GroupSerializer},
        examples=[
            OpenApiExample(
                "Change privacy", value={"privacy": "private"}, request_only=True
            )
        ],
        description="Change group privacy (public, private, secret). Only creator can do this.",
    )
    def patch(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if group.creator != request.user:
            return Response(
                {"detail": "Only the group creator can change privacy"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ChangePrivacyInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_privacy = serializer.validated_data["privacy"]
        try:
            updated_group = GroupService.change_privacy(group, new_privacy)
            return Response(
                GroupSerializer(updated_group, context={"request": request}).data
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GroupRecommendationsView(APIView):
    """View for group recommendations (already limited, not paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                description="Number of recommendations",
                required=False,
            ),
        ],
        responses={200: PaginatedGroupSerializer},
        description="Get group recommendations for the current user based on their interests/follows.",
    )
    def get(self, request):
        limit = int(request.query_params.get("limit", 10))
        recommendations = GroupService.get_recommended_groups(
            user=request.user, limit=limit
        )
        serializer = GroupSerializer(
            recommendations, many=True, context={"request": request}
        )
        return Response(serializer.data)


class GroupPopularView(APIView):
    """View for popular groups (already limited, not paginated)"""

    @extend_schema(
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
        responses={200: PaginatedGroupSerializer},
        description="Get popular groups based on recent activity and member count.",
    )
    def get(self, request):
        limit = int(request.query_params.get("limit", 10))
        min_members = int(request.query_params.get("min_members", 10))
        days = int(request.query_params.get("days", 30))
        popular_groups = GroupService.get_popular_groups(
            min_members=min_members, days=days, limit=limit
        )
        serializer = GroupSerializer(
            popular_groups, many=True, context={"request": request}
        )
        return Response(serializer.data)


class GroupSearchMembersView(APIView):
    """View for searching members within a group (paginated)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
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
        responses={200: PaginatedGroupMemberSerializer},
        description="Search members within a group by username or name.",
    )
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupService.is_user_allowed_to_view(request.user, group):
            return Response(
                {"detail": "You do not have permission to view members"},
                status=status.HTTP_403_FORBIDDEN,
            )
        query = request.query_params.get("query", "")
        if not query:
            return Response(
                {"detail": "query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        members = GroupMemberService.search_members(group=group, query=query)
        paginator = GroupsPagination()
        page = paginator.paginate_queryset(members, request)
        serializer = GroupMemberSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
