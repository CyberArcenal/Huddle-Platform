from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.contrib.contenttypes.models import ContentType
from typing import Optional, List, Dict, Any

from users.models import User
from ..models import Comment


class CommentService:
    """Generic service for Comment model operations."""

    @staticmethod
    def create_comment(
        user: User,
        content_object,
        content: str,
        parent_comment: Optional[Comment] = None,
    ) -> Comment:
        """Create a new comment on any object."""
        if not content.strip():
            raise ValidationError("Comment content cannot be empty.")

        # Check if the target object is deleted (if it has an is_deleted flag)
        if hasattr(content_object, "is_deleted") and content_object.is_deleted:
            raise ValidationError("Cannot comment on a deleted object.")

        try:
            with transaction.atomic():
                comment = Comment.objects.create(
                    user=user,
                    content_object=content_object,
                    parent_comment=parent_comment,
                    content=content,
                )
                return comment
        except IntegrityError as e:
            raise ValidationError(f"Failed to create comment: {str(e)}")

    @staticmethod
    def get_comment_by_id(comment_id: int) -> Optional[Comment]:
        try:
            return Comment.objects.get(id=comment_id)
        except Comment.DoesNotExist:
            return None

    @staticmethod
    def get_comments_for_object(
        content_object,
        include_replies: bool = True,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Comment]:
        """Get comments for a specific object."""
        content_type = ContentType.objects.get_for_model(content_object)
        queryset = Comment.objects.filter(
            content_type=content_type, object_id=content_object.pk
        )
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        if not include_replies:
            queryset = queryset.filter(parent_comment__isnull=True)
        return list(queryset.order_by("created_at")[offset : offset + limit])

    @staticmethod
    def get_user_comments(
        user: User, include_deleted: bool = False, limit: int = 50, offset: int = 0
    ) -> List[Comment]:
        queryset = Comment.objects.filter(user=user)
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        return list(queryset.order_by("-created_at")[offset : offset + limit])

    @staticmethod
    def get_comment_replies(
        comment: Comment,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Comment]:
        queryset = comment.replies.all()
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        return list(
            queryset.select_related("user").order_by("created_at")[
                offset : offset + limit
            ]
        )

    @staticmethod
    def update_comment(comment: Comment, new_content: str) -> Comment:
        if not new_content.strip():
            raise ValidationError("Comment content cannot be empty.")
        comment.content = new_content
        comment.save()
        return comment

    @staticmethod
    def delete_comment(comment: Comment, soft: bool = True) -> bool:
        try:
            if soft:
                comment.is_deleted = True
                comment.save(update_fields=["is_deleted"])
            else:
                comment.delete()
            return True
        except Exception:
            return False

    @staticmethod
    def restore_comment(comment: Comment) -> bool:
        if not comment.is_deleted:
            return False
        comment.is_deleted = False
        comment.save(update_fields=["is_deleted"])
        return True

    @staticmethod
    def get_comment_count(content_object, include_deleted: bool = False) -> int:
        content_type = ContentType.objects.get_for_model(content_object)
        queryset = Comment.objects.filter(
            content_type=content_type, object_id=content_object.pk
        )
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        return queryset.count()

    @staticmethod
    def get_comment_thread(
        comment: Comment, include_deleted: bool = False
    ) -> List[Comment]:
        """Get full thread (ancestors and descendants)."""
        thread = []
        # Ancestors
        current = comment
        while current:
            thread.insert(0, current)
            current = current.parent_comment

        # Descendants
        def add_replies(parent):
            replies = Comment.objects.filter(parent_comment=parent)
            if not include_deleted:
                replies = replies.filter(is_deleted=False)
            for reply in replies.order_by("created_at"):
                thread.append(reply)
                add_replies(reply)

        add_replies(comment)
        return thread

    @staticmethod
    def get_nested_comments(
        content_object, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Return nested comment tree for an object."""
        content_type = ContentType.objects.get_for_model(content_object)
        top_level = Comment.objects.filter(
            content_type=content_type,
            object_id=content_object.pk,
            parent_comment__isnull=True,
        )
        if not include_deleted:
            top_level = top_level.filter(is_deleted=False)
        top_level = top_level.order_by("created_at")

        def build_tree(comment):
            replies_queryset = comment.replies.all()
            if not include_deleted:
                replies_queryset = replies_queryset.filter(is_deleted=False)
            return {
                "comment": comment,
                "replies": [
                    build_tree(reply)
                    for reply in replies_queryset.order_by("created_at")
                ],
            }

        return [build_tree(c) for c in top_level]

    @staticmethod
    def search_comments(
        query: str,
        user: Optional[User] = None,
        content_object=None,
        include_deleted: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Comment]:
        queryset = Comment.objects.filter(content__icontains=query)
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        if user:
            queryset = queryset.filter(user=user)
        if content_object:
            content_type = ContentType.objects.get_for_model(content_object)
            queryset = queryset.filter(
                content_type=content_type, object_id=content_object.pk
            )
        return list(queryset.order_by("-created_at")[offset : offset + limit])

    @staticmethod
    def get_comment_statistics(comment: Comment, user: User = None) -> Dict[str, Any]:
        """Get reply count and like count for a comment."""
        from .reaction import ReactionService

        reply_count = comment.replies.filter(is_deleted=False).count()
        reaction_count = ReactionService.get_like_count("comment", comment.id)
        liked = ReactionService.has_liked(
            user=user, content_type=comment, object_id=comment.id
        ) if user else False
        reactions = ReactionService.get_reaction_counts(comment, comment.id)
        current_reaction = ReactionService.get_user_reaction(user, comment, comment.id) if user else None
        return {
            "comment_id": comment.id,
            "reply_count": reply_count,
            "reactions": reactions,
            "reaction_count": reaction_count,
            "liked": liked,
            "current_reaction": current_reaction,
            "created_at": comment.created_at,
            "has_parent": comment.parent_comment is not None,
            "content_object_id": comment.object_id,
            "content_type": comment.content_type.model,
        }
