from django.urls import path, include
from rest_framework.routers import DefaultRouter

from users.views.activity import ActivitySummaryView, FollowingActivityView, LogActivityView, RecentActivitiesView, UserActivityListView
from users.views.admin import AdminBulkUserActionView, AdminCleanupView, AdminCreateUserView, AdminDashboardView, AdminUserDetailView, AdminUserListView, UserExportView
from users.views.follow import FollowStatsView, FollowStatusView, FollowUserView, FollowersListView, FollowingListView, MutualFollowsView, SuggestedUsersView, UnfollowUserView
from users.views.media import CoverPhotoUploadView, GetCoverPhotoView, GetProfilePictureView, ProfilePictureUploadView, RemoveCoverPhotoView, RemoveProfilePictureView, ValidateImageUploadView
from users.views.search import AdvancedUserSearchView, GlobalSearchView, SearchAutocompleteView, SearchByEmailView, SearchByUsernameView, UserSearchView
from users.views.security import ActiveSessionsView, BulkTerminateSessionsView, ChangePasswordView, Check2FAStatusView, Disable2FAView, Enable2FAView, FailedLoginAttemptsView, SecurityLogsView, SecuritySettingsView, SuspiciousActivitiesView, TerminateAllSessionsView, TerminateSessionView
from users.views.user import CheckEmailView, CheckUsernameView, UserDeactivateView, UserDetailView, UserProfileView, UserRegisterView, UserStatusUpdateView, VerifyUserView

# Create a router for API views
router = DefaultRouter()

urlpatterns = [
    # User endpoints
    path('register/', UserRegisterView.as_view(), name='user-register'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('profile/<int:user_id>/', UserDetailView.as_view(), name='user-detail'),
    path('search/', UserSearchView.as_view(), name='user-search'),
    path('status/update/', UserStatusUpdateView.as_view(), name='user-status-update'),
    path('deactivate/', UserDeactivateView.as_view(), name='user-deactivate'),
    path('verify/', VerifyUserView.as_view(), name='user-verify'),
    path('check-username/', CheckUsernameView.as_view(), name='check-username'),
    path('check-email/', CheckEmailView.as_view(), name='check-email'),
    
    # Follow endpoints
    path('follow/', FollowUserView.as_view(), name='follow-user'),
    path('unfollow/', UnfollowUserView.as_view(), name='unfollow-user'),
    path('follow-status/<int:user_id>/', FollowStatusView.as_view(), name='follow-status'),
    path('follow-stats/', FollowStatsView.as_view(), name='follow-stats'),
    path('follow-stats/<int:user_id>/', FollowStatsView.as_view(), name='follow-stats-user'),
    path('followers/', FollowersListView.as_view(), name='followers-list'),
    path('followers/<int:user_id>/', FollowersListView.as_view(), name='followers-list-user'),
    path('following/', FollowingListView.as_view(), name='following-list'),
    path('following/<int:user_id>/', FollowingListView.as_view(), name='following-list-user'),
    path('mutual-follows/<int:user_id>/', MutualFollowsView.as_view(), name='mutual-follows'),
    path('suggested-users/', SuggestedUsersView.as_view(), name='suggested-users'),
    
    # Security endpoints
    path('security/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('security/enable-2fa/', Enable2FAView.as_view(), name='enable-2fa'),
    path('security/disable-2fa/', Disable2FAView.as_view(), name='disable-2fa'),
    path('security/settings/', SecuritySettingsView.as_view(), name='security-settings'),
    path('security/logs/', SecurityLogsView.as_view(), name='security-logs'),
    path('security/failed-logins/', FailedLoginAttemptsView.as_view(), name='failed-logins'),
    path('security/suspicious-activities/', SuspiciousActivitiesView.as_view(), name='suspicious-activities'),
    path('security/sessions/', ActiveSessionsView.as_view(), name='active-sessions'),
    path('security/terminate-session/', TerminateSessionView.as_view(), name='terminate-session'),
    path('security/bulk-terminate-sessions/', BulkTerminateSessionsView.as_view(), name='bulk-terminate-sessions'),
    path('security/terminate-all-sessions/', TerminateAllSessionsView.as_view(), name='terminate-all-sessions'),
    path('security/check-2fa/', Check2FAStatusView.as_view(), name='check-2fa'),
    
    # Activity endpoints
    path('activity/', UserActivityListView.as_view(), name='user-activity'),
    path('activity/following/', FollowingActivityView.as_view(), name='following-activity'),
    path('activity/summary/', ActivitySummaryView.as_view(), name='activity-summary'),
    path('activity/recent/', RecentActivitiesView.as_view(), name='recent-activities'),
    path('activity/log/', LogActivityView.as_view(), name='log-activity'),
    
    # Media endpoints
    path('media/profile-picture/', ProfilePictureUploadView.as_view(), name='upload-profile-picture'),
    path('media/cover-photo/', CoverPhotoUploadView.as_view(), name='upload-cover-photo'),
    path('media/remove-profile-picture/', RemoveProfilePictureView.as_view(), name='remove-profile-picture'),
    path('media/remove-cover-photo/', RemoveCoverPhotoView.as_view(), name='remove-cover-photo'),
    path('media/profile-picture/<int:user_id>/', GetProfilePictureView.as_view(), name='get-profile-picture'),
    path('media/cover-photo/<int:user_id>/', GetCoverPhotoView.as_view(), name='get-cover-photo'),
    path('media/validate-image/', ValidateImageUploadView.as_view(), name='validate-image'),
    
    # Search endpoints
    path('search/users/', UserSearchView.as_view(), name='search-users'),
    path('search/advanced/', AdvancedUserSearchView.as_view(), name='advanced-search'),
    path('search/autocomplete/', SearchAutocompleteView.as_view(), name='search-autocomplete'),
    path('search/by-username/', SearchByUsernameView.as_view(), name='search-by-username'),
    path('search/by-email/', SearchByEmailView.as_view(), name='search-by-email'),
    path('search/global/', GlobalSearchView.as_view(), name='global-search'),
    
    # Admin endpoints
    path('admin/users/', AdminUserListView.as_view(), name='admin-user-list'),
    path('admin/users/<int:user_id>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('admin/users/create/', AdminCreateUserView.as_view(), name='admin-create-user'),
    path('admin/bulk-action/', AdminBulkUserActionView.as_view(), name='admin-bulk-action'),
    path('admin/dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('admin/export/<int:user_id>/', UserExportView.as_view(), name='user-export'),
    path('admin/cleanup/', AdminCleanupView.as_view(), name='admin-cleanup'),
]