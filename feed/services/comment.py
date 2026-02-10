from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from typing import Optional, List, Dict, Any, Tuple
from ..models import Comment, Post, User


class CommentService:
    """Service for Comment model operations"""
    
    @staticmethod
    def create_comment(
        post: Post,
        user: User,
        content: str,
        parent_comment: Optional[Comment] = None
    ) -> Comment:
        """Create a new comment"""
        if not content.strip():
            raise ValidationError("Comment content cannot be empty")
        
        # Check if post is deleted
        if post.is_deleted:
            raise ValidationError("Cannot comment on a deleted post")
        
        try:
            with transaction.atomic():
                comment = Comment.objects.create(
                    post=post,
                    user=user,
                    parent_comment=parent_comment,
                    content=content
                )
                return comment
        except IntegrityError as e:
            raise ValidationError(f"Failed to create comment: {str(e)}")
    
    @staticmethod
    def get_comment_by_id(comment_id: int) -> Optional[Comment]:
        """Retrieve comment by ID"""
        try:
            return Comment.objects.get(id=comment_id)
        except Comment.DoesNotExist:
            return None
    
    @staticmethod
    def get_post_comments(
        post: Post,
        include_replies: bool = True,
        limit: int = 100,
        offset: int = 0
    ) -> List[Comment]:
        """Get comments for a post"""
        queryset = Comment.objects.filter(post=post)
        
        if not include_replies:
            queryset = queryset.filter(parent_comment__isnull=True)
        
        return list(queryset.order_by('created_at')[offset:offset + limit])
    
    @staticmethod
    def get_user_comments(
        user: User,
        limit: int = 50,
        offset: int = 0
    ) -> List[Comment]:
        """Get all comments by a user"""
        return list(
            Comment.objects.filter(user=user)
            .select_related('post')
            .order_by('-created_at')[offset:offset + limit]
        )
    
    @staticmethod
    def get_comment_replies(
        comment: Comment,
        limit: int = 50,
        offset: int = 0
    ) -> List[Comment]:
        """Get replies to a comment"""
        return list(
            comment.replies.all()
            .select_related('user')
            .order_by('created_at')[offset:offset + limit]
        )
    
    @staticmethod
    def update_comment(comment: Comment, new_content: str) -> Comment:
        """Update comment content"""
        if not new_content.strip():
            raise ValidationError("Comment content cannot be empty")
        
        comment.content = new_content
        comment.save()
        return comment
    
    @staticmethod
    def delete_comment(comment: Comment) -> bool:
        """Delete a comment"""
        try:
            comment.delete()
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_post_comment_count(post: Post) -> int:
        """Get total comment count for a post (including replies)"""
        return Comment.objects.filter(post=post).count()
    
    @staticmethod
    def get_comment_thread(comment: Comment) -> List[Comment]:
        """Get full comment thread (parent and all children)"""
        thread = []
        
        # Get all ancestors
        current = comment
        while current:
            thread.insert(0, current)
            current = current.parent_comment
        
        # Get all descendants (replies) using recursion
        def add_replies(parent):
            replies = Comment.objects.filter(parent_comment=parent).order_by('created_at')
            for reply in replies:
                thread.append(reply)
                add_replies(reply)
        
        add_replies(comment)
        
        return thread
    
    @staticmethod
    def get_nested_comments(post: Post) -> List[Dict[str, Any]]:
        """Get comments in nested structure for a post"""
        top_level_comments = Comment.objects.filter(
            post=post,
            parent_comment__isnull=True
        ).order_by('created_at')
        
        def build_comment_tree(comment):
            return {
                'comment': comment,
                'replies': [
                    build_comment_tree(reply)
                    for reply in comment.replies.all().order_by('created_at')
                ]
            }
        
        return [build_comment_tree(comment) for comment in top_level_comments]
    
    @staticmethod
    def search_comments(
        query: str,
        user: Optional[User] = None,
        post: Optional[Post] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Comment]:
        """Search comments by content"""
        queryset = Comment.objects.filter(content__icontains=query)
        
        if user:
            queryset = queryset.filter(user=user)
        
        if post:
            queryset = queryset.filter(post=post)
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_comment_statistics(comment: Comment) -> Dict[str, Any]:
        """Get statistics for a comment"""
        from .like import LikeService
        
        reply_count = comment.replies.count()
        like_count = LikeService.get_like_count('comment', comment.id)
        
        return {
            'comment_id': comment.id,
            'reply_count': reply_count,
            'like_count': like_count,
            'created_at': comment.created_at,
            'post_id': comment.post.id,
            'has_parent': comment.parent_comment is not None
        }