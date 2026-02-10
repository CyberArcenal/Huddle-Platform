from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from typing import Optional, List, Dict, Any, Tuple
from ..models import Post, User
import uuid


class PostService:
    """Service for Post model operations"""
    
    @staticmethod
    def create_post(
        user: User,
        content: str,
        post_type: str = 'text',
        media_url: Optional[str] = None,
        is_public: bool = True,
        **extra_fields
    ) -> Post:
        """Create a new post"""
        # Validate post type
        valid_types = [choice[0] for choice in Post.POST_TYPES]
        if post_type not in valid_types:
            raise ValidationError(f"Post type must be one of {valid_types}")
        
        # Validate based on post type
        if post_type == 'text' and not content.strip():
            raise ValidationError("Text posts require content")
        elif post_type in ['image', 'video'] and not media_url:
            raise ValidationError(f"{post_type.capitalize()} posts require media_url")
        
        try:
            with transaction.atomic():
                post = Post.objects.create(
                    user=user,
                    content=content,
                    post_type=post_type,
                    media_url=media_url,
                    is_public=is_public,
                    **extra_fields
                )
                return post
        except IntegrityError as e:
            raise ValidationError(f"Failed to create post: {str(e)}")
    
    @staticmethod
    def get_post_by_id(post_id: int) -> Optional[Post]:
        """Retrieve post by ID"""
        try:
            return Post.objects.get(id=post_id, is_deleted=False)
        except Post.DoesNotExist:
            return None
    
    @staticmethod
    def get_user_posts(
        user: User,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Post]:
        """Get posts by a specific user"""
        queryset = Post.objects.filter(user=user)
        
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_public_posts(
        exclude_user: Optional[User] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Post]:
        """Get public posts from all users"""
        queryset = Post.objects.filter(is_public=True, is_deleted=False)
        
        if exclude_user:
            queryset = queryset.exclude(user=exclude_user)
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_feed_posts(
        user: User,
        limit: int = 50,
        offset: int = 0
    ) -> List[Post]:
        """Get personalized feed posts for a user"""
        from users.services import UserFollowService
        
        # Get users that the current user follows
        following_users = UserFollowService.get_following(user)
        
        # Get posts from followed users and user's own posts
        feed_posts = Post.objects.filter(
            Q(user__in=following_users) | Q(user=user),
            is_deleted=False
        ).select_related('user').order_by('-created_at')[offset:offset + limit]
        
        return list(feed_posts)
    
    @staticmethod
    def update_post(post: Post, update_data: Dict[str, Any]) -> Post:
        """Update post information"""
        # Only allow update if post is not deleted
        if post.is_deleted:
            raise ValidationError("Cannot update a deleted post")
        
        try:
            with transaction.atomic():
                for field, value in update_data.items():
                    if hasattr(post, field) and field not in ['id', 'user', 'created_at']:
                        setattr(post, field, value)
                
                post.full_clean()
                post.save()
                return post
        except ValidationError as e:
            raise
    
    @staticmethod
    def delete_post(post: Post, soft_delete: bool = True) -> bool:
        """Delete a post (soft or hard delete)"""
        try:
            with transaction.atomic():
                if soft_delete:
                    post.is_deleted = True
                    post.save()
                else:
                    post.delete()
                return True
        except Exception:
            return False
    
    @staticmethod
    def restore_post(post: Post) -> bool:
        """Restore a soft-deleted post"""
        if not post.is_deleted:
            return False
        
        post.is_deleted = False
        post.save()
        return True
    
    @staticmethod
    def search_posts(
        query: str,
        user: Optional[User] = None,
        post_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Post]:
        """Search posts by content"""
        queryset = Post.objects.filter(
            content__icontains=query,
            is_deleted=False
        )
        
        if user:
            queryset = queryset.filter(user=user)
        
        if post_type:
            queryset = queryset.filter(post_type=post_type)
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_post_statistics(post: Post) -> Dict[str, Any]:
        """Get statistics for a post"""
        from .comment import CommentService
        from .like import LikeService
        
        comment_count = CommentService.get_post_comment_count(post)
        like_count = LikeService.get_like_count('post', post.id)
        
        return {
            'post_id': post.id,
            'comment_count': comment_count,
            'like_count': like_count,
            'created_at': post.created_at,
            'updated_at': post.updated_at,
            'is_public': post.is_public,
            'post_type': post.post_type
        }
    
    @staticmethod
    def get_user_post_statistics(user: User) -> Dict[str, Any]:
        """Get post statistics for a user"""
        total_posts = Post.objects.filter(user=user, is_deleted=False).count()
        public_posts = Post.objects.filter(user=user, is_public=True, is_deleted=False).count()
        private_posts = total_posts - public_posts
        
        # Post type breakdown
        type_breakdown = Post.objects.filter(user=user, is_deleted=False).values('post_type').annotate(
            count=Count('id')
        )
        
        return {
            'total_posts': total_posts,
            'public_posts': public_posts,
            'private_posts': private_posts,
            'type_breakdown': list(type_breakdown),
            'first_post_date': Post.objects.filter(user=user).order_by('created_at').first().created_at if total_posts > 0 else None
        }
    
    @staticmethod
    def get_trending_posts(
        hours: int = 24,
        min_likes: int = 5,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get trending posts (most liked within a time period)"""
        from .like import LikeService
        
        time_threshold = timezone.now() - timezone.timedelta(hours=hours)
        
        # Get posts created within the time period
        recent_posts = Post.objects.filter(
            created_at__gte=time_threshold,
            is_deleted=False,
            is_public=True
        )
        
        # Calculate like counts and filter
        trending = []
        for post in recent_posts:
            like_count = LikeService.get_like_count('post', post.id)
            if like_count >= min_likes:
                trending.append({
                    'post': post,
                    'like_count': like_count,
                    'comment_count': post.comments.count()
                })
        
        # Sort by like count (descending) and then by recency
        trending.sort(key=lambda x: (-x['like_count'], -x['post'].created_at.timestamp()))
        
        return trending[:limit]
    
    @staticmethod
    def cleanup_deleted_posts(days: int = 30) -> int:
        """Permanently delete posts that were soft-deleted more than X days ago"""
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        old_deleted_posts = Post.objects.filter(
            is_deleted=True,
            updated_at__lt=time_threshold
        )
        count = old_deleted_posts.count()
        old_deleted_posts.delete()
        
        return count