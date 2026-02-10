from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from typing import Optional, List, Dict, Any, Tuple
from ..models import Like, Post, Comment, User
import uuid


class LikeService:
    """Service for Like model operations"""
    
    CONTENT_TYPES = ['post', 'comment', 'story']
    
    @staticmethod
    def toggle_like(
        user: User,
        content_type: str,
        object_id: int
    ) -> Tuple[bool, Optional[Like]]:
        """Toggle like on an object (like/unlike)"""
        # Validate content type
        if content_type not in LikeService.CONTENT_TYPES:
            raise ValidationError(f"Content type must be one of {LikeService.CONTENT_TYPES}")
        
        try:
            with transaction.atomic():
                # Check if like already exists
                like = Like.objects.filter(
                    user=user,
                    content_type=content_type,
                    object_id=object_id
                ).first()
                
                if like:
                    # Unlike: delete the like
                    like.delete()
                    return False, None
                else:
                    # Like: create new like
                    like = Like.objects.create(
                        user=user,
                        content_type=content_type,
                        object_id=object_id
                    )
                    return True, like
        except IntegrityError as e:
            raise ValidationError(f"Failed to toggle like: {str(e)}")
    
    @staticmethod
    def add_like(
        user: User,
        content_type: str,
        object_id: int
    ) -> Tuple[bool, Optional[Like]]:
        """Add a like (does nothing if already liked)"""
        # Validate content type
        if content_type not in LikeService.CONTENT_TYPES:
            raise ValidationError(f"Content type must be one of {LikeService.CONTENT_TYPES}")
        
        try:
            with transaction.atomic():
                like, created = Like.objects.get_or_create(
                    user=user,
                    content_type=content_type,
                    object_id=object_id
                )
                return created, like if created else None
        except IntegrityError as e:
            raise ValidationError(f"Failed to add like: {str(e)}")
    
    @staticmethod
    def remove_like(
        user: User,
        content_type: str,
        object_id: int
    ) -> bool:
        """Remove a like (unlike)"""
        deleted_count, _ = Like.objects.filter(
            user=user,
            content_type=content_type,
            object_id=object_id
        ).delete()
        
        return deleted_count > 0
    
    @staticmethod
    def has_liked(
        user: User,
        content_type: str,
        object_id: int
    ) -> bool:
        """Check if user has liked an object"""
        return Like.objects.filter(
            user=user,
            content_type=content_type,
            object_id=object_id
        ).exists()
    
    @staticmethod
    def get_like_count(
        content_type: str,
        object_id: int
    ) -> int:
        """Get like count for an object"""
        return Like.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).count()
    
    @staticmethod
    def get_likes_for_object(
        content_type: str,
        object_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[Like]:
        """Get all likes for an object"""
        return list(
            Like.objects.filter(
                content_type=content_type,
                object_id=object_id
            ).select_related('user')
            .order_by('-created_at')[offset:offset + limit]
        )
    
    @staticmethod
    def get_user_likes(
        user: User,
        content_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Like]:
        """Get all likes by a user"""
        queryset = Like.objects.filter(user=user)
        
        if content_type:
            queryset = queryset.filter(content_type=content_type)
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_recent_likers(
        content_type: str,
        object_id: int,
        limit: int = 10
    ) -> List[User]:
        """Get recent users who liked an object"""
        likes = Like.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).select_related('user').order_by('-created_at')[:limit]
        
        return [like.user for like in likes]
    
    @staticmethod
    def get_mutual_likes(
        user1: User,
        user2: User,
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get mutual likes between two users"""
        # Posts that both users have liked
        user1_liked_posts = Like.objects.filter(
            user=user1,
            content_type='post'
        ).values_list('object_id', flat=True)
        
        user2_liked_posts = Like.objects.filter(
            user=user2,
            content_type='post'
        ).values_list('object_id', flat=True)
        
        mutual_post_ids = set(user1_liked_posts) & set(user2_liked_posts)
        
        # Comments that both users have liked
        user1_liked_comments = Like.objects.filter(
            user=user1,
            content_type='comment'
        ).values_list('object_id', flat=True)
        
        user2_liked_comments = Like.objects.filter(
            user=user2,
            content_type='comment'
        ).values_list('object_id', flat=True)
        
        mutual_comment_ids = set(user1_liked_comments) & set(user2_liked_comments)
        
        return {
            'mutual_posts': len(mutual_post_ids),
            'mutual_comments': len(mutual_comment_ids),
            'total_mutual_likes': len(mutual_post_ids) + len(mutual_comment_ids)
        }
    
    @staticmethod
    def get_most_liked_content(
        content_type: str,
        days: int = 7,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get most liked content of a specific type"""
        from django.db.models import Count
        
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        # Group likes by object_id and count
        liked_objects = Like.objects.filter(
            content_type=content_type,
            created_at__gte=time_threshold
        ).values('object_id').annotate(
            like_count=Count('id')
        ).order_by('-like_count')[:limit]
        
        # Fetch the actual objects based on content_type
        results = []
        for item in liked_objects:
            if content_type == 'post':
                try:
                    obj = Post.objects.get(id=item['object_id'], is_deleted=False)
                    results.append({
                        'object': obj,
                        'like_count': item['like_count'],
                        'type': 'post'
                    })
                except Post.DoesNotExist:
                    continue
            elif content_type == 'comment':
                try:
                    obj = Comment.objects.get(id=item['object_id'])
                    results.append({
                        'object': obj,
                        'like_count': item['like_count'],
                        'type': 'comment'
                    })
                except Comment.DoesNotExist:
                    continue
            # Add other content types as needed
        
        return results
    
    @staticmethod
    def get_user_like_statistics(user: User) -> Dict[str, Any]:
        """Get like statistics for a user"""
        total_likes_given = Like.objects.filter(user=user).count()
        
        # Breakdown by content type
        type_breakdown = Like.objects.filter(user=user).values('content_type').annotate(
            count=Count('id')
        )
        
        # Most liked content types
        most_liked_posts = Like.objects.filter(
            user=user,
            content_type='post'
        ).count()
        
        most_liked_comments = Like.objects.filter(
            user=user,
            content_type='comment'
        ).count()
        
        return {
            'total_likes_given': total_likes_given,
            'type_breakdown': list(type_breakdown),
            'most_liked_post_id': Like.objects.filter(
                user=user,
                content_type='post'
            ).values('object_id').annotate(
                count=Count('id')
            ).order_by('-count').first(),
            'first_like_date': Like.objects.filter(user=user).order_by('created_at').first().created_at if total_likes_given > 0 else None
        }