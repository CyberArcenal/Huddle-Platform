from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from typing import Optional, List, Dict, Any, Tuple

from feed.models.reaction import LIKE_CONTENT_TYPES, REACTION_TYPES
from users.models import User
from ..models import Reaction, Post, Comment


class ReactionService:
    SERVICE_REACTION_TYPES = [c[0] for c in REACTION_TYPES]
    SERVICE_CONTENT_TYPES = [c[0] for c in LIKE_CONTENT_TYPES]

    @staticmethod
    def set_reaction(
        user: User,
        content_type: str,
        object_id: int,
        reaction_type: Optional[str]
    ) -> Tuple[bool, Optional[Reaction]]:
        """
        Set a reaction.
        - If reaction_type is None → remove any existing reaction.
        - If same reaction exists → remove (toggle off).
        - If different reaction exists → update.
        - If no reaction → create new.
        Returns (changed, reaction_object).
        """
        if content_type not in ReactionService.SERVICE_CONTENT_TYPES:
            raise ValidationError(f"Invalid content type: {content_type}")

        if reaction_type and reaction_type not in ReactionService.SERVICE_REACTION_TYPES:
            raise ValidationError(f"Invalid reaction type: {reaction_type}")

        try:
            with transaction.atomic():
                reaction = Reaction.objects.filter(
                    user=user,
                    content_type=content_type,
                    object_id=object_id
                ).first()

                if reaction:
                    if reaction.reaction_type == reaction_type:
                        # Same reaction → remove
                        reaction.delete()
                        return False, None
                    elif reaction_type:
                        # Different reaction → update
                        reaction.reaction_type = reaction_type
                        reaction.save()
                        return True, reaction
                    else:
                        # Remove (reaction_type is None)
                        reaction.delete()
                        return False, None
                else:
                    if reaction_type:
                        # Create new
                        reaction = Reaction.objects.create(
                            user=user,
                            content_type=content_type,
                            object_id=object_id,
                            reaction_type=reaction_type
                        )
                        return True, reaction
                    else:
                        # No reaction and nothing to add
                        return False, None
        except IntegrityError as e:
            raise ValidationError(f"Failed to set reaction: {str(e)}")

    @staticmethod
    def get_user_reaction(user: User, content_type: str, object_id: int) -> Optional[str]:
        """Return the reaction type of a user on an object, or None."""
        reaction = Reaction.objects.filter(
            user=user,
            content_type=content_type,
            object_id=object_id
        ).first()
        return reaction.reaction_type if reaction else None

    @staticmethod
    def get_reaction_counts(content_type: str, object_id: int) -> Dict[str, Any]:
        """Return counts per reaction type for an object."""
        qs = Reaction.objects.filter(content_type=content_type, object_id=object_id)
        counts = qs.values('reaction_type').annotate(count=Count('id'))
        result = {rt: 0 for rt in ReactionService.SERVICE_REACTION_TYPES}
        for item in counts:
            result[item['reaction_type']] = item['count']
        return result

    @staticmethod
    def get_total_reactions(content_type: str, object_id: int) -> int:
        return Reaction.objects.filter(content_type=content_type, object_id=object_id).count()

    # ----- Legacy methods for 'like' only (backward compatibility) -----
    @staticmethod
    def toggle_like(user: User, content_type: str, object_id: int) -> Tuple[bool, Optional[Reaction]]:
        return ReactionService.set_reaction(user, content_type, object_id, 'like')

    @staticmethod
    def add_like(user: User, content_type: str, object_id: int) -> Tuple[bool, Optional[Reaction]]:
        return ReactionService.set_reaction(user, content_type, object_id, 'like')

    @staticmethod
    def remove_like(user: User, content_type: str, object_id: int) -> bool:
        deleted, _ = Reaction.objects.filter(
            user=user, content_type=content_type, object_id=object_id
        ).delete()
        return deleted > 0

    @staticmethod
    def has_liked(user: User, content_type: str, object_id: int) -> bool:
        return Reaction.objects.filter(
            user=user, content_type=content_type, object_id=object_id, reaction_type='like'
        ).exists()

    @staticmethod
    def get_like_count(content_type: str, object_id: int) -> int:
        return Reaction.objects.filter(
            content_type=content_type, object_id=object_id, reaction_type='like'
        ).count()

    # ----- Existing utility methods adapted to work with reactions -----
    @staticmethod
    def get_reactions_for_object(
        content_type: str,
        object_id: int,
        reaction_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Reaction]:
        """Get reactions for an object, optionally filtered by type."""
        queryset = Reaction.objects.filter(content_type=content_type, object_id=object_id)
        if reaction_type:
            queryset = queryset.filter(reaction_type=reaction_type)
        return list(queryset.select_related('user').order_by('-created_at')[offset:offset + limit])

    @staticmethod
    def get_user_reactions(
        user: User,
        content_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Reaction]:
        """Get all reactions by a user."""
        queryset = Reaction.objects.filter(user=user)
        if content_type:
            queryset = queryset.filter(content_type=content_type)
        return list(queryset.order_by('-created_at')[offset:offset + limit])

    @staticmethod
    def get_recent_reactors(
        content_type: str,
        object_id: int,
        reaction_type: Optional[str] = None,
        limit: int = 10
    ) -> List[User]:
        """Get recent users who reacted to an object."""
        queryset = Reaction.objects.filter(content_type=content_type, object_id=object_id)
        if reaction_type:
            queryset = queryset.filter(reaction_type=reaction_type)
        reactors = queryset.select_related('user').order_by('-created_at')[:limit]
        return [r.user for r in reactors]

    @staticmethod
    def get_mutual_reactions(
        user1: User,
        user2: User,
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get mutual reactions between two users."""
        # For backward compatibility, we focus on likes only, but can be extended.
        user1_liked_posts = Reaction.objects.filter(
            user=user1, content_type='post', reaction_type='like'
        ).values_list('object_id', flat=True)
        user2_liked_posts = Reaction.objects.filter(
            user=user2, content_type='post', reaction_type='like'
        ).values_list('object_id', flat=True)
        mutual_post_ids = set(user1_liked_posts) & set(user2_liked_posts)

        user1_liked_comments = Reaction.objects.filter(
            user=user1, content_type='comment', reaction_type='like'
        ).values_list('object_id', flat=True)
        user2_liked_comments = Reaction.objects.filter(
            user=user2, content_type='comment', reaction_type='like'
        ).values_list('object_id', flat=True)
        mutual_comment_ids = set(user1_liked_comments) & set(user2_liked_comments)

        return {
            'mutual_posts': len(mutual_post_ids),
            'mutual_comments': len(mutual_comment_ids),
            'total_mutual_likes': len(mutual_post_ids) + len(mutual_comment_ids)
        }

    @staticmethod
    def get_most_reacted_content(
        content_type: str,
        days: int = 7,
        limit: int = 10,
        reaction_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get most reacted content of a specific type, optionally filtered by reaction type."""
        from django.db.models import Count

        time_threshold = timezone.now() - timezone.timedelta(days=days)
        queryset = Reaction.objects.filter(
            content_type=content_type,
            created_at__gte=time_threshold
        )
        if reaction_type:
            queryset = queryset.filter(reaction_type=reaction_type)

        reacted_objects = queryset.values('object_id').annotate(
            reaction_count=Count('id')
        ).order_by('-reaction_count')[:limit]

        results = []
        for item in reacted_objects:
            if content_type == 'post':
                try:
                    obj = Post.objects.get(id=item['object_id'], is_deleted=False)
                    results.append({
                        'object': obj,
                        'reaction_count': item['reaction_count'],
                        'type': 'post'
                    })
                except Post.DoesNotExist:
                    continue
            elif content_type == 'comment':
                try:
                    obj = Comment.objects.get(id=item['object_id'])
                    results.append({
                        'object': obj,
                        'reaction_count': item['reaction_count'],
                        'type': 'comment'
                    })
                except Comment.DoesNotExist:
                    continue
        return results

    @staticmethod
    def get_user_reaction_statistics(user: User) -> Dict[str, Any]:
        """Get reaction statistics for a user."""
        total_reactions = Reaction.objects.filter(user=user).count()
        type_breakdown = Reaction.objects.filter(user=user).values('content_type', 'reaction_type').annotate(
            count=Count('id')
        )
        # Breakdown by content type (for backward compatibility)
        content_type_breakdown = Reaction.objects.filter(user=user).values('content_type').annotate(
            count=Count('id')
        )

        return {
            'total_reactions': total_reactions,
            'type_breakdown': list(type_breakdown),
            'content_type_breakdown': list(content_type_breakdown),
            'first_reaction_date': Reaction.objects.filter(user=user).order_by('created_at').first().created_at if total_reactions > 0 else None
        }