# services/group_suggestion.py
from typing import List, Dict, Optional
from django.db import models
from django.db.models import Count, Q, Value, Case, When, F
from django.db.models.functions import Coalesce
from groups.models import Group, GroupMember, GROUP_TYPE_CHOICES
from users.models import User


class GroupSuggestionService:
    """
    Comprehensive group suggestion service using profile, friends, popularity, and collaborative filtering.
    """

    @staticmethod
    def suggest_by_profile(
        user: User,
        limit: int = 10,
        offset: int = 0,
        include_types: Optional[List[str]] = None,
        exclude_joined: bool = True,
    ) -> List[Group]:
        """
        Suggest groups based on user's profile attributes (hobbies, interests, etc.).
        Returns groups ordered by relevance (number of matching attributes).
        """
        if include_types is None:
            include_types = [choice[0] for choice in GROUP_TYPE_CHOICES]

        # Base queryset
        qs = Group.objects.all()

        # Exclude groups the user is already a member of
        if exclude_joined:
            joined_group_ids = GroupMember.objects.filter(user=user).values_list('group_id', flat=True)
            qs = qs.exclude(id__in=joined_group_ids)

        # Filter by group types if provided
        if include_types:
            qs = qs.filter(group_type__in=include_types)

        # Prepare the relevance score annotation
        conditions = []

        # Hobbies: group name matches any of user's hobbies
        hobby_names = list(user.hobbies.values_list('name', flat=True))
        if hobby_names:
            conditions.append(
                When(name__in=hobby_names, then=Value(1))
            )

        # Interests
        interest_names = list(user.interests.values_list('name', flat=True))
        if interest_names:
            conditions.append(
                When(name__in=interest_names, then=Value(1))
            )

        # Causes
        cause_names = list(user.causes.values_list('name', flat=True))
        if cause_names:
            conditions.append(
                When(name__in=cause_names, then=Value(1))
            )

        # Schools
        school_names = list(user.schools.values_list('name', flat=True))
        if school_names:
            conditions.append(
                When(name__in=school_names, then=Value(1))
            )

        # Works
        work_names = list(user.works.values_list('name', flat=True))
        if work_names:
            conditions.append(
                When(name__in=work_names, then=Value(1))
            )

        # Personality type (match in name or description)
        if user.personality_type:
            conditions.append(
                When(Q(name__icontains=user.personality_type) | Q(description__icontains=user.personality_type), then=Value(1))
            )

        # Location (if user has location, match city/area in group name/description)
        if user.location:
            # Simple substring match (can be improved with geocoding)
            location_parts = user.location.split(',')
            for part in location_parts:
                part = part.strip()
                if part:
                    conditions.append(
                        When(Q(name__icontains=part) | Q(description__icontains=part), then=Value(1))
                    )

        # If no conditions, return empty
        if not conditions:
            return []

        # Annotate with relevance score
        qs = qs.annotate(
            relevance_score=Coalesce(
                sum(Case(condition, default=Value(0)) for condition in conditions),
                Value(0)
            )
        ).filter(relevance_score__gt=0).order_by('-relevance_score')

        # Paginate
        return list(qs[offset:offset+limit])

    @staticmethod
    def suggest_by_friends(
        user: User,
        limit: int = 10,
        offset: int = 0,
        exclude_joined: bool = True,
    ) -> List[Dict]:
        """
        Suggest groups that the user's friends (people they follow) have joined.
        Returns a list of groups with count of friends who joined.
        """
        from users.models import UserFollow

        # Get users that current user follows
        followed_ids = UserFollow.objects.filter(follower=user).values_list('following_id', flat=True)
        if not followed_ids:
            return []

        # Groups joined by those friends
        qs = Group.objects.filter(
            memberships__user_id__in=followed_ids
        ).distinct()

        if exclude_joined:
            joined_group_ids = GroupMember.objects.filter(user=user).values_list('group_id', flat=True)
            qs = qs.exclude(id__in=joined_group_ids)

        # Annotate with friend count (how many friends joined)
        qs = qs.annotate(
            friend_joined_count=Count('memberships', filter=models.Q(memberships__user_id__in=followed_ids))
        ).order_by('-friend_joined_count')

        # Paginate
        groups = qs[offset:offset+limit]
        return [{'group': g, 'friend_joined_count': g.friend_joined_count} for g in groups]

    @staticmethod
    def suggest_popular(
        user: User,
        limit: int = 10,
        offset: int = 0,
        group_type: Optional[str] = None,
        exclude_joined: bool = True,
    ) -> List[Group]:
        """
        Suggest groups with the highest member count, optionally filtered by type.
        """
        qs = Group.objects.all()
        if group_type:
            qs = qs.filter(group_type=group_type)
        if exclude_joined:
            joined_group_ids = GroupMember.objects.filter(user=user).values_list('group_id', flat=True)
            qs = qs.exclude(id__in=joined_group_ids)
        qs = qs.order_by('-member_count')
        return list(qs[offset:offset+limit])

    @staticmethod
    def suggest_by_similar_members(
        user: User,
        limit: int = 10,
        offset: int = 0,
        exclude_joined: bool = True,
    ) -> List[Group]:
        """
        Suggest groups that are frequently joined by members who are also in groups the user is in.
        Uses collaborative filtering: groups that have high overlap in membership with groups the user belongs to.
        """
        # Get groups the user is in
        user_group_ids = GroupMember.objects.filter(user=user).values_list('group_id', flat=True)
        if not user_group_ids:
            return []

        # Find members of those groups
        member_user_ids = GroupMember.objects.filter(group_id__in=user_group_ids).values_list('user_id', flat=True).distinct()

        # Find groups that those members are in (excluding user's groups)
        qs = Group.objects.filter(
            memberships__user_id__in=member_user_ids
        ).distinct()

        if exclude_joined:
            qs = qs.exclude(id__in=user_group_ids)

        # Annotate with overlap score: number of distinct members that are also members of user's groups
        qs = qs.annotate(
            overlap_count=Count('memberships', filter=models.Q(memberships__user_id__in=member_user_ids))
        ).order_by('-overlap_count')

        return list(qs[offset:offset+limit])

    @classmethod
    def get_combined_suggestions(
        cls,
        user: User,
        limit_profile: int = 5,
        limit_friends: int = 5,
        limit_popular: int = 5,
        limit_collab: int = 5,
        include_types: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        """
        Return a dictionary with separate lists for each suggestion type.
        """
        return {
            "profile_based": cls.suggest_by_profile(
                user, limit=limit_profile, include_types=include_types
            ),
            "from_friends": cls.suggest_by_friends(user, limit=limit_friends),
            "popular": cls.suggest_popular(user, limit=limit_popular),
            "similar_members": cls.suggest_by_similar_members(user, limit=limit_collab),
        }

    @classmethod
    def get_ranked_recommendations(
        cls,
        user: User,
        limit: int = 20,
        offset: int = 0,
        include_profile: bool = True,
        include_friends: bool = True,
        include_popular: bool = True,
        include_collab: bool = True,
    ) -> List[Dict]:
        """
        Return a single ranked list of groups combining multiple suggestion sources,
        each with a score and a reason. Scores are normalized across sources.
        """
        suggestions = []

        if include_profile:
            profile_groups = cls.suggest_by_profile(user, limit=limit*2, offset=0)
            for group in profile_groups:
                score = getattr(group, 'relevance_score', 1)
                suggestions.append({
                    'group': group,
                    'score': score,
                    'reason': 'Based on your profile'
                })

        if include_friends:
            friend_suggestions = cls.suggest_by_friends(user, limit=limit*2, offset=0)
            for item in friend_suggestions:
                # weight friend count higher
                score = item['friend_joined_count'] * 2
                suggestions.append({
                    'group': item['group'],
                    'score': score,
                    'reason': f"{item['friend_joined_count']} of your friends joined this group"
                })

        if include_popular:
            popular_groups = cls.suggest_popular(user, limit=limit*2, offset=0)
            for group in popular_groups:
                # normalize member count to a score between 0 and 10
                score = min(group.member_count / 100, 10)  # cap at 10
                suggestions.append({
                    'group': group,
                    'score': score,
                    'reason': 'Popular group'
                })

        if include_collab:
            collab_groups = cls.suggest_by_similar_members(user, limit=limit*2, offset=0)
            for group in collab_groups:
                score = getattr(group, 'overlap_count', 1)
                suggestions.append({
                    'group': group,
                    'score': score,
                    'reason': f"Members of groups you joined also joined this"
                })

        # Deduplicate by group id, keep highest score
        unique = {}
        for s in suggestions:
            gid = s['group'].id
            if gid not in unique or s['score'] > unique[gid]['score']:
                unique[gid] = s

        # Sort by score descending
        unique_list = sorted(unique.values(), key=lambda x: x['score'], reverse=True)

        # Paginate
        paginated = unique_list[offset:offset+limit]
        return paginated