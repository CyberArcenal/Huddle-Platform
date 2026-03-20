from django.urls import path

from groups.views.base import (
    GroupDetailView,
    GroupJoinView,
    GroupLeaveView,
    GroupListView,
    GroupMemberRoleView,
    GroupMembersView,
    GroupPopularView,
    GroupPrivacyView,
    GroupSearchMembersView,
    GroupStatisticsView,
    GroupTransferOwnershipView,
)
from groups.views.group_suggestion import GroupSuggestionView

app_name = "groups"

urlpatterns = [
    # Group CRUD operations
    path("", GroupListView.as_view(), name="group-list"),
    path("<int:group_id>/", GroupDetailView.as_view(), name="group-detail"),
    # Group members management
    path("<int:group_id>/members/", GroupMembersView.as_view(), name="group-members"),
    path("<int:group_id>/members/<int:user_id>/", GroupMembersView.as_view(), name="group-members-delete"),
    path(
        "<int:group_id>/members/<int:user_id>/role/",
        GroupMemberRoleView.as_view(),
        name="member-role",
    ),
    path(
        "<int:group_id>/members/search/",
        GroupSearchMembersView.as_view(),
        name="search-members",
    ),
    # Group join/leave
    path("<int:group_id>/join/", GroupJoinView.as_view(), name="group-join"),
    path("<int:group_id>/leave/", GroupLeaveView.as_view(), name="group-leave"),
    # Group statistics and management
    path(
        "<int:group_id>/statistics/",
        GroupStatisticsView.as_view(),
        name="group-statistics",
    ),
    path(
        "<int:group_id>/transfer-ownership/",
        GroupTransferOwnershipView.as_view(),
        name="transfer-ownership",
    ),
    path("<int:group_id>/privacy/", GroupPrivacyView.as_view(), name="change-privacy"),
    # Discovery and recommendations
    path("popular/", GroupPopularView.as_view(), name="popular-groups"),
    
    path("suggestions/", GroupSuggestionView.as_view(), name="group-suggestions"),
]
