import django.urls
import rest_framework.routers
import users.serializers.user_preference
import users.views.activity
import users.views.admin
import users.views.block
import users.views.follow
import users.views.friendship
import users.views.suggestions
import users.views.media
import users.views.search
import users.views.security
import users.views.user
import users.views.user_media
from .login import urlpatterns as login_urlpatterns
from .login_checkpoint import urlpatterns as checkpoint
from .reset import urlpatterns as password_urlpatterns
# Create a router for API views
router = rest_framework.routers.DefaultRouter()

urlpatterns = [
    # User endpoints
    django.urls.path('register/', users.views.user.UserRegisterView.as_view(), name='user-register'),
    django.urls.path('profile/', users.views.user.UserProfileView.as_view(), name='user-profile'),
    django.urls.path('profile/<int:user_id>/', users.views.user.UserDetailView.as_view(), name='user-detail'),
    django.urls.path('search/', users.views.search.UserSearchView.as_view(), name='user-search'),
    django.urls.path('status/update/', users.views.user.UserStatusUpdateView.as_view(), name='user-status-update'),
    django.urls.path('deactivate/', users.views.user.UserDeactivateView.as_view(), name='user-deactivate'),
    django.urls.path('verify/', users.views.user.VerifyUserView.as_view(), name='user-verify'),
    django.urls.path('check-username/', users.views.user.CheckUsernameView.as_view(), name='check-username'),
    django.urls.path('check-email/', users.views.user.CheckEmailView.as_view(), name='check-email'),
    django.urls.path('verify-email/', users.views.user.EmailVerificationView.as_view(), name='verify-email'),
    django.urls.path('resend-verification/', users.views.user.ResendVerificationView.as_view(), name='resend-verification'),
    
    # Follow endpoints
    django.urls.path('follow/', users.views.follow.FollowUserView.as_view(), name='follow-user'),
    django.urls.path('unfollow/', users.views.follow.UnfollowUserView.as_view(), name='unfollow-user'),
    django.urls.path('follow-status/<int:user_id>/', users.views.follow.FollowStatusView.as_view(), name='follow-status'),
    django.urls.path('follow-stats/', users.views.follow.FollowStatsView.as_view(), name='follow-stats'),
    django.urls.path('follow-stats/<int:user_id>/', users.views.follow.FollowStatsView.as_view(), name='follow-stats-user'),
    django.urls.path('followers/', users.views.follow.FollowersListView.as_view(), name='followers-list'),
    django.urls.path('followers/<int:user_id>/', users.views.follow.FollowersListView.as_view(), name='followers-list-user'),
    django.urls.path('following/', users.views.follow.FollowingListView.as_view(), name='following-list'),
    django.urls.path('following/<int:user_id>/', users.views.follow.FollowingListView.as_view(), name='following-list-user'),
    django.urls.path('mutual-follows/<int:user_id>/', users.views.follow.MutualFollowsView.as_view(), name='mutual-follows'),
    django.urls.path('suggested-users/', users.views.follow.SuggestedUsersView.as_view(), name='suggested-users'),

    django.urls.path('mutual-friends/', users.views.follow.MutualFriendsView.as_view(), name='mutual-friends'),
    django.urls.path('popular-users/', users.views.follow.PopularUsersView.as_view(), name='popular-users'),
    
    django.urls.path('friend-suggestions/', users.views.suggestions.UserFriendSuggestionsView.as_view(), name='friend-suggestions'),

    
    # Security endpoints
    django.urls.path('security/change-password/', users.views.security.ChangePasswordView.as_view(), name='change-password'),
    django.urls.path('security/enable-2fa/', users.views.security.Enable2FAView.as_view(), name='enable-2fa'),
    django.urls.path('security/disable-2fa/', users.views.security.Disable2FAView.as_view(), name='disable-2fa'),
    django.urls.path('security/settings/', users.views.security.SecuritySettingsView.as_view(), name='security-settings'),
    django.urls.path('security/logs/', users.views.security.SecurityLogsView.as_view(), name='security-logs'),
    django.urls.path('security/failed-logins/', users.views.security.FailedLoginAttemptsView.as_view(), name='failed-logins'),
    django.urls.path('security/suspicious-activities/', users.views.security.SuspiciousActivitiesView.as_view(), name='suspicious-activities'),
    django.urls.path('security/sessions/', users.views.security.ActiveSessionsView.as_view(), name='active-sessions'),
    django.urls.path('security/terminate-session/', users.views.security.TerminateSessionView.as_view(), name='terminate-session'),
    django.urls.path('security/bulk-terminate-sessions/', users.views.security.BulkTerminateSessionsView.as_view(), name='bulk-terminate-sessions'),
    django.urls.path('security/terminate-all-sessions/', users.views.security.TerminateAllSessionsView.as_view(), name='terminate-all-sessions'),
    django.urls.path('security/check-2fa/', users.views.security.Check2FAStatusView.as_view(), name='check-2fa'),
    
    # Activity endpoints
    django.urls.path('activity/', users.views.activity.UserActivityListView.as_view(), name='user-activity'),
    django.urls.path('activity/following/', users.views.activity.FollowingActivityView.as_view(), name='following-activity'),
    django.urls.path('activity/summary/', users.views.activity.ActivitySummaryView.as_view(), name='activity-summary'),
    django.urls.path('activity/recent/', users.views.activity.RecentActivitiesView.as_view(), name='recent-activities'),
    django.urls.path('activity/log/', users.views.activity.LogActivityView.as_view(), name='log-activity'),
    
    # Media endpoints
    django.urls.path('media/profile-picture/', users.views.media.ProfilePictureUploadView.as_view(), name='upload-profile-picture'),
    django.urls.path('media/cover-photo/', users.views.media.CoverPhotoUploadView.as_view(), name='upload-cover-photo'),
    django.urls.path('media/remove-profile-picture/', users.views.media.RemoveProfilePictureView.as_view(), name='remove-profile-picture'),
    django.urls.path('media/remove-cover-photo/', users.views.media.RemoveCoverPhotoView.as_view(), name='remove-cover-photo'),
    django.urls.path('media/profile-picture/<int:user_id>/', users.views.media.GetProfilePictureView.as_view(), name='get-profile-picture'),
    django.urls.path('media/cover-photo/<int:user_id>/', users.views.media.GetCoverPhotoView.as_view(), name='get-cover-photo'),
    
    django.urls.path('users/<int:user_id>/media/', users.views.user_media.UserMediaGridView.as_view(), name='user-media'),
    django.urls.path('me/media/', users.views.user_media.UserMediaGridView.as_view(), name='my-media'),
    
    # Search endpoints
    django.urls.path('search/users/', users.views.search.UserSearchView.as_view(), name='search-users'),
    django.urls.path('search/advanced/', users.views.search.AdvancedUserSearchView.as_view(), name='advanced-search'),
    django.urls.path('search/autocomplete/', users.views.search.SearchAutocompleteView.as_view(), name='search-autocomplete'),
    django.urls.path('search/by-username/', users.views.search.SearchByUsernameView.as_view(), name='search-by-username'),
    django.urls.path('search/by-email/', users.views.search.SearchByEmailView.as_view(), name='search-by-email'),
    django.urls.path('search/global/', users.views.search.GlobalSearchView.as_view(), name='global-search'),
    
    # Admin endpoints
    django.urls.path('admin/users/', users.views.admin.AdminUserListView.as_view(), name='admin-user-list'),
    django.urls.path('admin/users/<int:user_id>/', users.views.admin.AdminUserDetailView.as_view(), name='admin-user-detail'),
    django.urls.path('admin/users/create/', users.views.admin.AdminCreateUserView.as_view(), name='admin-create-user'),
    django.urls.path('admin/bulk-action/', users.views.admin.AdminBulkUserActionView.as_view(), name='admin-bulk-action'),
    django.urls.path('admin/dashboard/', users.views.admin.AdminDashboardView.as_view(), name='admin-dashboard'),
    django.urls.path('admin/export/<int:user_id>/', users.views.admin.UserExportView.as_view(), name='user-export'),
    django.urls.path('admin/cleanup/', users.views.admin.AdminCleanupView.as_view(), name='admin-cleanup'),
]


urlpatterns += [
    django.urls.path("auth/", django.urls.include(login_urlpatterns)),
    django.urls.path("password/", django.urls.include(password_urlpatterns)),
    django.urls.path("auth-checkpoints/", django.urls.include(checkpoint)),
]


urlpatterns += [
    # Preference endpoints
    django.urls.path('preferences/hobbies/', users.serializers.user_preference.UserHobbiesView.as_view(), name='user-hobbies'),
    django.urls.path('preferences/interests/', users.serializers.user_preference.UserInterestsView.as_view(), name='user-interests'),
    django.urls.path('preferences/favorites/', users.serializers.user_preference.UserFavoritesView.as_view(), name='user-favorites'),
    django.urls.path('preferences/music/', users.serializers.user_preference.UserMusicView.as_view(), name='user-music'),
    django.urls.path('preferences/works/', users.serializers.user_preference.UserWorksView.as_view(), name='user-works'),
    django.urls.path('preferences/schools/', users.serializers.user_preference.UserSchoolsView.as_view(), name='user-schools'),
    django.urls.path('preferences/achievements/', users.serializers.user_preference.UserAchievementsView.as_view(), name='user-achievements'),
    django.urls.path('preferences/causes/', users.serializers.user_preference.UserCausesView.as_view(), name='user-causes'),
    django.urls.path('preferences/lifestyle-tags/', users.serializers.user_preference.UserLifestyleTagsView.as_view(), name='user-lifestyle-tags'),
]

urlpatterns += [
    django.urls.path('blocks/', users.views.block.BlockedUsersListView.as_view(), name='blocked-list'),
    django.urls.path('blocks/block/', users.views.block.BlockView.as_view(), name='block'),
    django.urls.path('blocks/unblock/', users.views.block.UnblockView.as_view(), name='unblock'),
    django.urls.path('blocks/check/<int:user_id>/', users.views.block.CheckBlockedView.as_view(), name='check-blocked'),
]

urlpatterns += [
    django.urls.path('friends/', users.views.friendship.FriendsListView.as_view(), name='friends-list'),
    django.urls.path('friends/requests/send/', users.views.friendship.FriendRequestSendView.as_view(), name='friend-request-send'),
    django.urls.path('friends/requests/pending/', users.views.friendship.PendingRequestsView.as_view(), name='pending-requests'),
    django.urls.path('friends/requests/<int:pk>/accept/', users.views.friendship.FriendRequestAcceptView.as_view(), name='friend-request-accept'),
    django.urls.path('friends/requests/<int:pk>/decline/', users.views.friendship.FriendRequestDeclineView.as_view(), name='friend-request-decline'),
    django.urls.path('friends/remove/', users.views.friendship.FriendRemoveView.as_view(), name='friend-remove'),
    django.urls.path('friends/<int:pk>/tag/', users.views.friendship.FriendTagUpdateView.as_view(), name='friend-tag-update'),
]