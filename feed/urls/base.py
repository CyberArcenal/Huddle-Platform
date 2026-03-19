# feed/urls.py

from django.urls import path, include
from feed.views import comment, post, reaction, share
from feed.views import reel

urlpatterns = [
    # Post URLs
    path('posts/', post.PostListView.as_view(), name='post-list'),
    path('posts/search/', post.PostSearchView.as_view(), name='post-search'),
    path('posts/trending/', post.TrendingPostsView.as_view(), name='trending-posts'),
    path('posts/<int:post_id>/', post.PostDetailView.as_view(), name='post-detail'),
    path('posts/<int:post_id>/statistics/', post.PostStatisticsView.as_view(), name='post-statistics'),
    path('posts/<int:post_id>/restore/', post.PostRestoreView.as_view(), name='post-restore'),
    path('posts/<int:post_id>/share-to-group/', post.SharePostToGroupView.as_view(), name='post-share-to-group'),
    
    # User post statistics
    path('users/<int:user_id>/post-statistics/', post.UserPostStatisticsView.as_view(), name='user-post-statistics'),
    path('users/me/post-statistics/', post.UserPostStatisticsView.as_view(), name='my-post-statistics'),
    
    # Comment URLs
    path('comments/', comment.CommentListView.as_view(), name='comment-list'),
    path('comments/search/', comment.CommentSearchView.as_view(), name='comment-search'),
    path('comments/<int:comment_id>/', comment.CommentDetailView.as_view(), name='comment-detail'),
    path('comments/<int:comment_id>/replies/', comment.CommentRepliesView.as_view(), name='comment-replies'),
    path('comments/<int:comment_id>/thread/', comment.CommentThreadView.as_view(), name='comment-thread'),
    
    # Post-specific comment URLs
    path('posts/<int:post_id>/comments/', comment.CommentListView.as_view(), name='post-comment-list'),
    path('posts/<int:post_id>/comments/<int:comment_id>/replies/', comment.CommentRepliesView.as_view(), name='post-comment-replies'),
    
    # Like URLs
    path('likes/', reaction.LikeListView.as_view(), name='like-list'),
    path('likes/toggle/', reaction.LikeToggleView.as_view(), name='like-toggle'),
    path('likes/<int:like_id>/', reaction.LikeDetailView.as_view(), name='like-detail'),
    path('likes/check/<str:content_type>/<int:object_id>/', reaction.LikeCheckView.as_view(), name='like-check'),
    
    # Object-specific like URLs
    path('likes/<str:content_type>/<int:object_id>/', reaction.ObjectLikesView.as_view(), name='object-likes'),
    path('likes/<str:content_type>/<int:object_id>/recent/', reaction.RecentLikersView.as_view(), name='recent-likers'),
    
    # Statistics and analytics
    path('likes/most-liked/<str:content_type>/', reaction.MostLikedContentView.as_view(), name='most-liked'),
    path('likes/statistics/', reaction.UserLikeStatisticsView.as_view(), name='my-like-statistics'),
    path('likes/statistics/<int:user_id>/', reaction.UserLikeStatisticsView.as_view(), name='user-like-statistics'),
    path('likes/mutual/<int:user_id>/', reaction.MutualLikesView.as_view(), name='mutual-likes'),
    path('reactions/', reaction.ReactionView.as_view(), name='reaction-set'),
    

    # ==================== Reels ====================
    # Main reel endpoints
    path('reels/', reel.ReelListView.as_view(), name='reel-list'),
    path('reels/search/', reel.ReelSearchView.as_view(), name='reel-search'),
    path('reels/trending/', reel.TrendingReelsView.as_view(), name='trending-reels'),  # optional
    path('reels/<int:reel_id>/', reel.ReelDetailView.as_view(), name='reel-detail'),
    path('reels/<int:reel_id>/statistics/', reel.ReelStatisticsView.as_view(), name='reel-statistics'),
    path('reels/<int:reel_id>/restore/', reel.ReelRestoreView.as_view(), name='reel-restore'),

    # User reel statistics
    path('users/<int:user_id>/reel-statistics/', reel.UserReelStatisticsView.as_view(), name='user-reel-statistics'),
    path('users/me/reel-statistics/', reel.UserReelStatisticsView.as_view(), name='my-reel-statistics'),

    
    
    # ====================== SHARE =============================
    
    path('shares/', share.ShareListView.as_view(), name='share-list'),
    path('shares/<int:share_id>/', share.ShareDetailView.as_view(), name='share-detail'),
    path('shares/object/', share.ShareObjectSharesView.as_view(), name='share-object-list'),
    path('shares/statistics/user/', share.ShareUserStatisticsView.as_view(), name='share-user-stats'),
    path('shares/<int:share_id>/restore/', share.ShareRestoreView.as_view(), name='share-restore'),
]

app_name = 'feed'