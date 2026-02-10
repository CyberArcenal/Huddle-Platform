# feed/urls.py

from django.urls import path, include
from feed.views import comment, post, like
urlpatterns = [
    # Post URLs
    path('posts/', post.PostListView.as_view(), name='post-list'),
    path('posts/search/', post.PostSearchView.as_view(), name='post-search'),
    path('posts/trending/', post.TrendingPostsView.as_view(), name='trending-posts'),
    path('posts/<int:post_id>/', post.PostDetailView.as_view(), name='post-detail'),
    path('posts/<int:post_id>/statistics/', post.PostStatisticsView.as_view(), name='post-statistics'),
    path('posts/<int:post_id>/restore/', post.PostRestoreView.as_view(), name='post-restore'),
    
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
    path('likes/', like.LikeListView.as_view(), name='like-list'),
    path('likes/toggle/', like.LikeToggleView.as_view(), name='like-toggle'),
    path('likes/<int:like_id>/', like.LikeDetailView.as_view(), name='like-detail'),
    path('likes/check/<str:content_type>/<int:object_id>/', like.LikeCheckView.as_view(), name='like-check'),
    
    # Object-specific like URLs
    path('likes/<str:content_type>/<int:object_id>/', like.ObjectLikesView.as_view(), name='object-likes'),
    path('likes/<str:content_type>/<int:object_id>/recent/', like.RecentLikersView.as_view(), name='recent-likers'),
    
    # Statistics and analytics
    path('likes/most-liked/<str:content_type>/', like.MostLikedContentView.as_view(), name='most-liked'),
    path('likes/statistics/', like.UserLikeStatisticsView.as_view(), name='my-like-statistics'),
    path('likes/statistics/<int:user_id>/', like.UserLikeStatisticsView.as_view(), name='user-like-statistics'),
    path('likes/mutual/<int:user_id>/', like.MutualLikesView.as_view(), name='mutual-likes'),
]

# For including in main urls.py
app_name = 'feed'