# feed/views/post_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from feed.models import Post
from feed.serializers.post import PostDetailSerializer, PostFeedSerializer, PostSerializer, PostStatisticsSerializer, SearchSerializer, UserPostStatisticsSerializer
from feed.services import PostService
from global_utils.pagination import StandardResultsSetPagination
from users.models import User


class PostListView(APIView):
    """View for listing and creating posts"""
    
    def get_permissions(self):
        """Set permissions based on request method"""
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        user_posts = request.query_params.get('user_id')
        feed = request.query_params.get('feed', 'false').lower() == 'true'

        try:
            if user_posts:
                target_user = get_object_or_404(User, id=user_posts)
                posts = PostService.get_user_posts(user=target_user)   # no limit/offset
            elif feed and user:
                posts = PostService.get_feed_posts(user=user)           # no limit/offset
            else:
                posts = PostService.get_public_posts(exclude_user=user) # no limit/offset

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(posts, request)
            serializer = PostFeedSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request):
        """Create a new post"""
        serializer = PostSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            # Ensure user_id matches authenticated user
            if request.data.get('user_id') != request.user.id:
                return Response(
                    {'error': 'Cannot create post for another user'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            post = serializer.save()
            return Response(
                PostSerializer(post, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PostDetailView(APIView):
    """View for retrieving, updating, and deleting a specific post"""
    
    def get_permissions(self):
        """Set permissions based on request method"""
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get_object(self, post_id):
        """Get post object or return 404"""
        post = PostService.get_post_by_id(post_id)
        if not post:
            return None
        return post
    
    def get(self, request, post_id):
        """Retrieve a specific post"""
        post = self.get_object(post_id)
        if not post:
            return Response(
                {'error': 'Post not found or deleted'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if post is public
        if not post.is_public and request.user != post.user:
            return Response(
                {'error': 'You do not have permission to view this post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = PostDetailSerializer(
            post,
            context={'request': request}
        )
        return Response(serializer.data)
    
    def put(self, request, post_id):
        """Update a post"""
        post = self.get_object(post_id)
        if not post:
            return Response(
                {'error': 'Post not found or deleted'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check ownership
        if request.user != post.user:
            return Response(
                {'error': 'You do not have permission to update this post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = PostSerializer(
            post,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        
        if serializer.is_valid():
            # Ensure user_id doesn't change
            if 'user_id' in request.data and request.data['user_id'] != post.user.id:
                return Response(
                    {'error': 'Cannot change post owner'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            updated_post = serializer.save()
            return Response(
                PostSerializer(updated_post, context={'request': request}).data
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, post_id):
        """Delete a post (soft delete by default)"""
        post = self.get_object(post_id)
        if not post:
            return Response(
                {'error': 'Post not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check ownership
        if request.user != post.user:
            return Response(
                {'error': 'You do not have permission to delete this post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if hard delete requested
        hard_delete = request.query_params.get('hard', 'false').lower() == 'true'
        
        success = PostService.delete_post(post, soft_delete=not hard_delete)
        if success:
            message = "Post deleted successfully"
            if hard_delete:
                message = "Post permanently deleted"
            return Response({'message': message})
        
        return Response(
            {'error': 'Failed to delete post'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class PostStatisticsView(APIView):
    """View for post statistics"""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, post_id):
        """Get statistics for a specific post"""
        post = get_object_or_404(Post, id=post_id, is_deleted=False)
        
        # Check if user can view statistics
        if not post.is_public and request.user != post.user:
            return Response(
                {'error': 'You do not have permission to view statistics for this post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        statistics = PostService.get_post_statistics(post)
        serializer = PostStatisticsSerializer(statistics)
        return Response(serializer.data)


class UserPostStatisticsView(APIView):
    """View for user's post statistics"""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, user_id=None):
        """Get post statistics for a user"""
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            # Allow viewing own statistics or public user statistics
            if request.user != target_user:
                # Here you could add logic to check if user allows others to see their stats
                pass
        else:
            target_user = request.user
        
        statistics = PostService.get_user_post_statistics(target_user)
        serializer = UserPostStatisticsSerializer(statistics)
        return Response(serializer.data)


class PostSearchView(APIView):
    """View for searching posts"""
    
    def get_permissions(self):
        """Set permissions based on request method"""
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get(self, request):
        serializer = SearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = request.user if request.user.is_authenticated else None
        posts = PostService.search_posts(
            query=data['query'],
            user=user,
            post_type=data.get('post_type')
        )   # no limit/offset

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(posts, request)
        results = PostFeedSerializer(page, many=True).data
        return paginator.get_paginated_response(results)


class TrendingPostsView(APIView):
    """View for trending posts"""
    
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Get trending posts"""
        hours = int(request.query_params.get('hours', 24))
        min_likes = int(request.query_params.get('min_likes', 5))
        limit = int(request.query_params.get('limit', 10))
        
        trending = PostService.get_trending_posts(
            hours=hours,
            min_likes=min_likes,
            limit=limit
        )
        
        # Custom serialization for trending data
        data = []
        for item in trending:
            data.append({
                'post': PostFeedSerializer(item['post']).data,
                'like_count': item['like_count'],
                'comment_count': item['comment_count']
            })
        
        return Response({
            'timeframe_hours': hours,
            'min_likes': min_likes,
            'results': data
        })


class PostRestoreView(APIView):
    """View for restoring deleted posts"""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, post_id):
        """Restore a soft-deleted post"""
        post = get_object_or_404(Post, id=post_id)
        
        # Check ownership
        if request.user != post.user:
            return Response(
                {'error': 'You do not have permission to restore this post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        success = PostService.restore_post(post)
        if success:
            return Response({
                'message': 'Post restored successfully',
                'post': PostSerializer(post, context={'request': request}).data
            })
        
        return Response(
            {'error': 'Post is not deleted or could not be restored'},
            status=status.HTTP_400_BAD_REQUEST
        )