from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Count, Model
from django.contrib.contenttypes.models import ContentType
from typing import Optional, List, Dict, Any, Tuple, Type, Union
from django.db.models import Q
from users.models import User
from users.models.user_follow import UserFollow
from ..models import Reaction, Post, Comment
from feed.models.reaction import REACTION_TYPES  # keeps the list of valid reaction types


class ReactionService:
    # Optional: keep a list of allowed model names if you want to restrict
    # ALLOWED_CONTENT_TYPES = ['post', 'comment', 'story', 'reel', 'reel_comment']
    SERVICE_REACTION_TYPES = [rt[0] for rt in REACTION_TYPES]

    @staticmethod
    def _get_content_type(model: Union[str, Type[Model], Model]) -> ContentType:
        """
        Helper to fetch a ContentType by model name (string),
        model class, or model instance.
        Raises ValidationError if the content type does not exist.
        """
        try:
            if isinstance(model, str):
                # lookup by model name string
                return ContentType.objects.get(model=model.lower())
            else:
                # lookup by model class or instance
                return ContentType.objects.get_for_model(model)
        except ContentType.DoesNotExist:
            raise ValidationError(f"Invalid content type: '{model}'")

    @staticmethod
    def _validate_reaction_type(reaction_type: Optional[str]) -> None:
        """Raise ValidationError if reaction_type is not in the allowed list."""
        if reaction_type and reaction_type not in ReactionService.SERVICE_REACTION_TYPES:
            raise ValidationError(f"Invalid reaction type: '{reaction_type}'")

    @staticmethod
    def set_reaction(
        user: User,
        content_type: str,
        object_id: int,
        reaction_type: Optional[str]
    ) -> Tuple[bool, Optional[Reaction]]:
        """
        Set a reaction on any object.
        - If reaction_type is None → remove any existing reaction.
        - If same reaction exists → remove (toggle off).
        - If different reaction exists → update.
        - If no reaction → create new.
        Returns (changed, reaction_object). 'changed' is True if a reaction was added/updated.
        """
        ct = ReactionService._get_content_type(content_type)
        ReactionService._validate_reaction_type(reaction_type)

        try:
            with transaction.atomic():
                reaction = Reaction.objects.filter(
                    user=user,
                    content_type=ct,
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
                            content_type=ct,
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
        ct = ReactionService._get_content_type(content_type)
        reaction = Reaction.objects.filter(
            user=user,
            content_type=ct,
            object_id=object_id
        ).first()
        return reaction.reaction_type if reaction else None

    @staticmethod
    def get_reaction_counts(content_type: str, object_id: int) -> Dict[str, int]:
        """Return counts per reaction type for an object."""
        ct = ReactionService._get_content_type(content_type)
        qs = Reaction.objects.filter(content_type=ct, object_id=object_id)
        counts = qs.values('reaction_type').annotate(count=Count('id'))
        result = {rt: 0 for rt in ReactionService.SERVICE_REACTION_TYPES}
        for item in counts:
            result[item['reaction_type']] = item['count']
        return result

    @staticmethod
    def get_total_reactions(content_type: str, object_id: int) -> int:
        """Return total number of reactions (any type) on an object."""
        ct = ReactionService._get_content_type(content_type)
        return Reaction.objects.filter(content_type=ct, object_id=object_id).count()

    # ----- Legacy methods for 'like' only (backward compatibility) -----
    @staticmethod
    def toggle_like(user: User, content_type: str, object_id: int) -> Tuple[bool, Optional[Reaction]]:
        """Convenience: toggle a like (same as set_reaction with reaction_type='like')."""
        return ReactionService.set_reaction(user, content_type, object_id, 'like')

    @staticmethod
    def add_like(user: User, content_type: str, object_id: int) -> Tuple[bool, Optional[Reaction]]:
        """Convenience: add a like (same as set_reaction with reaction_type='like')."""
        return ReactionService.set_reaction(user, content_type, object_id, 'like')

    @staticmethod
    def remove_like(user: User, content_type: str, object_id: int) -> bool:
        """Remove a like (if any). Returns True if a like was removed."""
        ct = ReactionService._get_content_type(content_type)
        deleted, _ = Reaction.objects.filter(
            user=user, content_type=ct, object_id=object_id, reaction_type='like'
        ).delete()
        return deleted > 0

    @staticmethod
    def has_liked(user: User, content_type: str, object_id: int) -> bool:
        """Check if a user has liked the object."""
        ct = ReactionService._get_content_type(content_type)
        return Reaction.objects.filter(
            user=user, content_type=ct, object_id=object_id, reaction_type='like'
        ).exists()

    @staticmethod
    def get_like_count(content_type: str, object_id: int) -> int:
        """Return the number of likes on an object."""
        ct = ReactionService._get_content_type(content_type)
        return Reaction.objects.filter(
            content_type=ct, object_id=object_id, reaction_type='like'
        ).count()

    # ----- Utility methods for retrieving reactions and reactors -----
    @staticmethod
    def get_reactions_for_object(
        content_type: str,
        object_id: int,
        reaction_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Reaction]:
        """
        Get reactions for a specific object, optionally filtered by reaction type.
        Returns a list of Reaction objects with user prefetched.
        """
        ct = ReactionService._get_content_type(content_type)
        queryset = Reaction.objects.filter(content_type=ct, object_id=object_id)
        if reaction_type:
            ReactionService._validate_reaction_type(reaction_type)
            queryset = queryset.filter(reaction_type=reaction_type)
        return list(queryset.select_related('user').order_by('-created_at')[offset:offset + limit])

    @staticmethod
    def get_user_reactions(
        user: User,
        content_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Reaction]:
        """
        Get all reactions made by a user, optionally filtered by content type.
        """
        queryset = Reaction.objects.filter(user=user)
        if content_type:
            ct = ReactionService._get_content_type(content_type)
            queryset = queryset.filter(content_type=ct)
        return list(queryset.order_by('-created_at')[offset:offset + limit])

    @staticmethod
    def get_recent_reactors(
        content_type: str,
        object_id: int,
        reaction_type: Optional[str] = None,
        limit: int = 10
    ) -> List[User]:
        """
        Get the most recent users who reacted to an object.
        """
        ct = ReactionService._get_content_type(content_type)
        queryset = Reaction.objects.filter(content_type=ct, object_id=object_id)
        if reaction_type:
            ReactionService._validate_reaction_type(reaction_type)
            queryset = queryset.filter(reaction_type=reaction_type)
        reactors = queryset.select_related('user').order_by('-created_at')[:limit]
        return [r.user for r in reactors]

    @staticmethod
    def get_mutual_reactions(
        user1: User,
        user2: User,
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get mutual reactions (currently only likes) between two users.
        If content_type is given, only consider that type; otherwise consider all.
        Returns counts of mutual likes per content type and total.
        """
        # Base queryset for each user
        qs1 = Reaction.objects.filter(user=user1, reaction_type='like')
        qs2 = Reaction.objects.filter(user=user2, reaction_type='like')

        if content_type:
            ct = ReactionService._get_content_type(content_type)
            qs1 = qs1.filter(content_type=ct)
            qs2 = qs2.filter(content_type=ct)

        # For simplicity, we group by content type. This could be extended to any reaction type.
        # We'll fetch the object ids and compute intersection.
        # To avoid too many queries, we could do it per content type, but for now we'll assume limited data.
        mutual_counts = {}

        # Get distinct content types involved
        content_types = set(qs1.values_list('content_type', flat=True)) | set(qs2.values_list('content_type', flat=True))
        for ct_id in content_types:
            ct = ContentType.objects.get_for_id(ct_id)
            model_name = ct.model
            ids1 = set(qs1.filter(content_type=ct).values_list('object_id', flat=True))
            ids2 = set(qs2.filter(content_type=ct).values_list('object_id', flat=True))
            mutual_counts[model_name] = len(ids1 & ids2)

        total = sum(mutual_counts.values())
        return {
            **mutual_counts,
            'total_mutual_likes': total
        }

    @staticmethod
    def get_most_reacted_content(
        content_type: str,
        days: int = 7,
        limit: int = 10,
        reaction_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get the most reacted objects of a given content type within the last `days`.
        Each result contains the actual object (Post, Comment, etc.) and the reaction count.
        """
        ct = ReactionService._get_content_type(content_type)
        time_threshold = timezone.now() - timezone.timedelta(days=days)

        queryset = Reaction.objects.filter(
            content_type=ct,
            created_at__gte=time_threshold
        )
        if reaction_type:
            ReactionService._validate_reaction_type(reaction_type)
            queryset = queryset.filter(reaction_type=reaction_type)

        reacted_objects = queryset.values('object_id').annotate(
            reaction_count=Count('id')
        ).order_by('-reaction_count')[:limit]

        # Now fetch the actual objects (model class is known via ContentType)
        model_class = ct.model_class()
        results = []
        for item in reacted_objects:
            try:
                obj = model_class.objects.get(id=item['object_id'])
                # Optionally respect a soft-delete flag if the model has one
                # if hasattr(obj, 'is_deleted') and obj.is_deleted:
                #     continue
                results.append({
                    'object': obj,
                    'reaction_count': item['reaction_count'],
                    'type': content_type
                })
            except model_class.DoesNotExist:
                continue
        return results
    
    @staticmethod
    def get_friends_who_reacted_to_post(
        user: User,
        post_id: int,
        content_type: str = "post",
        reaction_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Return mutual-follow friends who reacted to a given post.
        - Friends are users who both follow and are followed by `user`.
        - Returns list of dicts: {'user': User, 'reaction_type': str, 'created_at': datetime}
        - Ordered by reaction created_at (most recent first).
        """
        # Resolve content type
        ct = ReactionService._get_content_type(content_type)

        # Get ids the user follows and ids who follow the user
        following_ids = set(UserFollow.objects.filter(follower=user).values_list("following_id", flat=True))
        follower_ids = set(UserFollow.objects.filter(following=user).values_list("follower_id", flat=True))

        # Mutual follows = friends
        friend_ids = list(following_ids & follower_ids)
        if not friend_ids:
            return []

        # Query reactions by those friends
        reaction_qs = Reaction.objects.filter(
            content_type=ct,
            object_id=post_id,
            user_id__in=friend_ids,
        )
        if reaction_type:
            ReactionService._validate_reaction_type(reaction_type)
            reaction_qs = reaction_qs.filter(reaction_type=reaction_type)

        reactions = reaction_qs.select_related("user").order_by("-created_at")[offset: offset + limit]

        # Build result with metadata
        result: List[Dict[str, Any]] = []
        for r in reactions:
            result.append({
                "user": r.user,
                "reaction_type": r.reaction_type,
                "created_at": r.created_at,
            })

        return result
    
    @staticmethod
    def get_user_reactions_queryset(user: User, content_type: Optional[str] = None):
        """
        Returns a queryset of reactions made by a user, optionally filtered by content type.
        """
        queryset = Reaction.objects.filter(user=user)
        if content_type:
            ct = ReactionService._get_content_type(content_type)
            queryset = queryset.filter(content_type=ct)
        return queryset

    @staticmethod
    def get_user_reaction_statistics(user: User) -> Dict[str, Any]:
        """
        Get statistics about a user's reactions.
        """
        reactions = Reaction.objects.filter(user=user)
        total = reactions.count()

        # Breakdown by reaction type
        type_breakdown = list(reactions.values('reaction_type').annotate(count=Count('id')))

        # Breakdown by content type (using model name for readability)
        # We need to join with ContentType to get the model name
        content_type_breakdown = list(
            reactions.values('content_type__model').annotate(count=Count('id'))
        )
        # Rename key for clarity
        for item in content_type_breakdown:
            item['content_type'] = item.pop('content_type__model')

        first_reaction = reactions.order_by('created_at').first()
        first_reaction_date = first_reaction.created_at if first_reaction else None

        return {
            'total_reactions': total,
            'type_breakdown': type_breakdown,
            'content_type_breakdown': content_type_breakdown,
            'first_reaction_date': first_reaction_date
        }