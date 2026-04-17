# services/matching.py
import math
from typing import List, Dict, Optional, Tuple, Set
from datetime import date

from django.db.models import Count, Q, OuterRef, Prefetch
from django.conf import settings

from users.models.user import User, UserStatus
from users.models.blocked import BlockedUser
from users.models.friendship import Friendship
from users.models.mute import MutedUser
from users.models.user_follow import UserFollow


class MatchingService:
    DEFAULT_WEIGHTS = {
        "personality_compatible": 3,
        "personality_same": 1,
        "love_language_match": 2,
        "relationship_goal_match": 2,
        "hobby_overlap": 1,
        "interest_overlap": 1,
        "music_overlap": 1,
        "cause_overlap": 1,
        "favorite_overlap": 0.5,
        "work_overlap": 0.5,
        "school_overlap": 0.5,
        "lifestyle_tag_overlap": 0.5,
        "achievement_overlap": 0.5,
        "location_proximity": 5,
        "age_match": 3,
    }

    MBTI_COMPATIBILITY = {
        "ISTJ": ["ESFP", "ESTP", "ENFP"],
        "ISFJ": ["ENTP", "ENFP", "ESTP"],
        "INFJ": ["ENFP", "ENTP", "INTJ"],
        "INTJ": ["ENFP", "ENTJ", "INFJ"],
        "ISTP": ["ESFP", "ESTP", "ENFP"],
        "ISFP": ["ENFJ", "ESFJ", "ENFP"],
        "INFP": ["ENFJ", "ENTJ", "ENFP"],
        "INTP": ["ENTJ", "ENFP", "ENTP"],
        "ESTP": ["ISFJ", "INFJ", "ENFP"],
        "ESFP": ["ISTJ", "INTJ", "ENFP"],
        "ENFP": ["INFJ", "INTJ", "ENTJ"],
        "ENTP": ["INFJ", "ISFJ", "ENFP"],
        "ESTJ": ["ISFP", "INFP", "ESFJ"],
        "ESFJ": ["ISFP", "INFP", "ENFP"],
        "ENFJ": ["INFP", "ISFP", "ENFP"],
        "ENTJ": ["INTP", "ENFP", "INFJ"],
    }

    @classmethod
    def get_weights(cls) -> Dict[str, float]:
        return getattr(settings, "MATCHING_WEIGHTS", cls.DEFAULT_WEIGHTS)

    # ----------------------------------------------------------------------
    # Helper methods
    # ----------------------------------------------------------------------
    @staticmethod
    def calculate_age(birth_date: Optional[date]) -> Optional[int]:
        if not birth_date:
            return None
        today = date.today()
        return today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )

    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
        if None in (lat1, lon1, lat2, lon2):
            return None
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
            math.radians(lat2)
        ) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @classmethod
    def get_excluded_user_ids(cls, user: User) -> Set[int]:
        """
        Returns a set of user IDs that should never be shown to the given user:
        - Self
        - Users blocked by the current user
        - Users who have blocked the current user
        - Users muted by the current user
        - Already accepted friends
        - Users with a pending friend request (either direction)
        """
        excluded = {user.id}

        # Blocked (user blocked someone)
        blocked_by_me = BlockedUser.objects.filter(user=user).values_list("blocked_id", flat=True)
        excluded.update(blocked_by_me)

        # Blocked by others (someone blocked user)
        blocked_me = BlockedUser.objects.filter(blocked=user).values_list("user_id", flat=True)
        excluded.update(blocked_me)

        # Muted by user
        muted_by_me = MutedUser.objects.filter(user=user).values_list("muted_id", flat=True)
        excluded.update(muted_by_me)

        # Friendship exclusions: accepted friends or any pending request
        # Friend requests where user is the sender
        sent_requests = Friendship.objects.filter(from_user=user).values_list("to_user_id", flat=True)
        # Friend requests where user is the receiver (pending or accepted)
        received_requests = Friendship.objects.filter(to_user=user).values_list("from_user_id", flat=True)
        # Also include accepted friends (status='accepted')
        accepted_friends = Friendship.objects.filter(
            Q(from_user=user, status="accepted") | Q(to_user=user, status="accepted")
        ).values_list("from_user_id", "to_user_id")
        friend_ids = set()
        for from_id, to_id in accepted_friends:
            friend_ids.add(from_id if from_id != user.id else to_id)
        excluded.update(sent_requests)
        excluded.update(received_requests)
        excluded.update(friend_ids)

        return excluded

    # ----------------------------------------------------------------------
    # Core scoring
    # ----------------------------------------------------------------------
    @classmethod
    def calculate_match_score(
        cls,
        user: User,
        candidate: User,
        max_distance_km: Optional[float] = None,
        preferred_age_range: Optional[Tuple[int, int]] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[int, List[str]]:
        """
        Returns (score, reasons) for the match between user and candidate.
        """
        if weights is None:
            weights = cls.get_weights()

        score = 0.0
        reasons = []

        # Personality
        if user.personality_type and candidate.personality_type:
            if candidate.personality_type == user.personality_type:
                pts = weights.get("personality_same", 1)
                score += pts
                reasons.append(f"Same personality type ({user.personality_type}) +{pts}")
            elif candidate.personality_type in cls.MBTI_COMPATIBILITY.get(user.personality_type, []):
                ptc = weights.get("personality_compatible", 3)
                score += ptc
                reasons.append(
                    f"Compatible personality type ({user.personality_type} with {candidate.personality_type}) +{ptc}"
                )

        # Love language
        if user.love_language and user.love_language == candidate.love_language:
            ll = weights.get("love_language_match", 2)
            score += ll
            reasons.append(f"Same love language ({user.love_language}) +{ll}")

        # Relationship goal
        if user.relationship_goal and user.relationship_goal == candidate.relationship_goal:
            rg = weights.get("relationship_goal_match", 2)
            score += rg
            reasons.append(f"Same relationship goal ({user.relationship_goal}) +{rg}")

        # Overlap counts (many-to-many)
        hobby_overlap = user.hobbies.filter(id__in=candidate.hobbies.all()).count()
        if hobby_overlap:
            ho = hobby_overlap * weights.get("hobby_overlap", 1)
            score += ho
            reasons.append(f"{hobby_overlap} common hobbies +{ho}")

        interest_overlap = user.interests.filter(id__in=candidate.interests.all()).count()
        if interest_overlap:
            io = interest_overlap * weights.get("interest_overlap", 1)
            score += io
            reasons.append(f"{interest_overlap} common interests +{io}")

        music_overlap = user.favorite_music.filter(id__in=candidate.favorite_music.all()).count()
        if music_overlap:
            mo = music_overlap * weights.get("music_overlap", 1)
            score += mo
            reasons.append(f"{music_overlap} common music tastes +{mo}")

        cause_overlap = user.causes.filter(id__in=candidate.causes.all()).count()
        if cause_overlap:
            co = cause_overlap * weights.get("cause_overlap", 1)
            score += co
            reasons.append(f"{cause_overlap} common causes +{co}")

        favorite_overlap = user.favorites.filter(id__in=candidate.favorites.all()).count()
        if favorite_overlap:
            fo = favorite_overlap * weights.get("favorite_overlap", 0.5)
            score += fo
            reasons.append(f"{favorite_overlap} common favorites +{fo}")

        work_overlap = user.works.filter(id__in=candidate.works.all()).count()
        if work_overlap:
            wo = work_overlap * weights.get("work_overlap", 0.5)
            score += wo
            reasons.append(f"{work_overlap} common works +{wo}")

        school_overlap = user.schools.filter(id__in=candidate.schools.all()).count()
        if school_overlap:
            so = school_overlap * weights.get("school_overlap", 0.5)
            score += so
            reasons.append(f"{school_overlap} common schools +{so}")

        lifestyle_overlap = user.lifestyle_tags.filter(id__in=candidate.lifestyle_tags.all()).count()
        if lifestyle_overlap:
            lso = lifestyle_overlap * weights.get("lifestyle_tag_overlap", 0.5)
            score += lso
            reasons.append(f"{lifestyle_overlap} common lifestyle tags +{lso}")

        achievement_overlap = user.achievements.filter(id__in=candidate.achievements.all()).count()
        if achievement_overlap:
            ao = achievement_overlap * weights.get("achievement_overlap", 0.5)
            score += ao
            reasons.append(f"{achievement_overlap} common achievements +{ao}")

        # Location proximity
        if (
            max_distance_km is not None
            and user.latitude
            and user.longitude
            and candidate.latitude
            and candidate.longitude
        ):
            distance = cls.calculate_distance(
                user.latitude, user.longitude, candidate.latitude, candidate.longitude
            )
            if distance is not None and distance <= max_distance_km:
                lp = weights.get("location_proximity", 5) * (1 - distance / max_distance_km)
                score += lp
                reasons.append(f"Within {distance:.1f} km +{lp:.1f}")

        # Age match
        if preferred_age_range and user.date_of_birth:
            age = cls.calculate_age(user.date_of_birth)
            if age is not None and preferred_age_range[0] <= age <= preferred_age_range[1]:
                am = weights.get("age_match", 3)
                score += am
                reasons.append(f"Within age range ({age} years) +{am}")

        return int(score), reasons

    # ----------------------------------------------------------------------
    # Match discovery
    # ----------------------------------------------------------------------
    @classmethod
    def get_matches(
        cls,
        user: User,
        limit: int = 20,
        offset: int = 0,
        max_distance_km: Optional[float] = None,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
        max_candidates: int = 500,
    ) -> List[Dict]:
        """
        Returns a list of potential matches (users not already connected),
        sorted by descending score.
        Each dict: {"user": User, "score": int, "reasons": List[str]}
        """
        # Base queryset: active users, not excluded
        excluded_ids = cls.get_excluded_user_ids(user)
        qs = (
            User.objects.filter(status=UserStatus.ACTIVE)
            .exclude(id__in=excluded_ids)
            .prefetch_related(
                "hobbies",
                "interests",
                "favorites",
                "favorite_music",
                "works",
                "schools",
                "achievements",
                "causes",
                "lifestyle_tags",
            )
        )

        # Age filtering (approximate)
        if min_age is not None or max_age is not None:
            today = date.today()
            if min_age is not None:
                max_birth_date = date(today.year - min_age, today.month, today.day)
                qs = qs.filter(date_of_birth__lte=max_birth_date)
            if max_age is not None:
                min_birth_date = date(today.year - max_age, today.month, today.day)
                qs = qs.filter(date_of_birth__gte=min_birth_date)

        # Distance bounding box (quick filter)
        if max_distance_km is not None and user.latitude and user.longitude:
            lat_delta = max_distance_km / 111.0
            lon_delta = max_distance_km / (111.0 * math.cos(math.radians(user.latitude)))
            qs = qs.filter(
                latitude__isnull=False,
                longitude__isnull=False,
                latitude__gte=user.latitude - lat_delta,
                latitude__lte=user.latitude + lat_delta,
                longitude__gte=user.longitude - lon_delta,
                longitude__lte=user.longitude + lon_delta,
            )

        # Limit candidate pool for performance
        candidates = list(qs[:max_candidates])

        results = []
        preferred_age_range = (min_age, max_age) if min_age is not None and max_age is not None else None
        for candidate in candidates:
            score, reasons = cls.calculate_match_score(
                user,
                candidate,
                max_distance_km=max_distance_km,
                preferred_age_range=preferred_age_range,
            )
            if score > 0:
                results.append({"user": candidate, "score": score, "reasons": reasons})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[offset : offset + limit]

    @classmethod
    def get_suggested_users(
        cls,
        user: User,
        limit: int = 20,
        offset: int = 0,
        min_mutual: int = 1,
    ) -> List[Dict]:
        """
        Suggests users that are friends of friends (followers of people the user follows)
        and who are not already connected, blocked, etc.
        Returns list of dicts: {"user": User, "mutual_count": int, "reason": str}
        """
        # People the user follows
        following_ids = UserFollow.objects.filter(follower=user).values_list("following_id", flat=True)
        if not following_ids:
            return []

        # Users that are followed by at least one of the people the user follows
        # (i.e., friends of friends)
        candidates_qs = User.objects.filter(
            id__in=UserFollow.objects.filter(follower_id__in=following_ids).values_list(
                "following_id", flat=True
            )
        )

        # Exclude self and already connected users
        excluded_ids = cls.get_excluded_user_ids(user)
        candidates_qs = candidates_qs.exclude(id__in=excluded_ids)

        # Annotate mutual friends count: how many of the user's followings also follow this candidate
        mutual_subquery = UserFollow.objects.filter(
            follower_id__in=following_ids, following=OuterRef("id")
        ).values("following").annotate(cnt=Count("id")).values("cnt")
        candidates_qs = candidates_qs.annotate(
            mutual_count=Count(
                "followers",
                filter=Q(followers__follower_id__in=following_ids),
                distinct=True,
            )
        ).filter(mutual_count__gte=min_mutual).order_by("-mutual_count")

        # Prefetch to avoid N+1 when serializing
        candidates_qs = candidates_qs.prefetch_related(
            "hobbies",
            "interests",
            "favorites",
            "favorite_music",
            "works",
            "schools",
            "achievements",
            "causes",
            "lifestyle_tags",
        )

        paginated = candidates_qs[offset : offset + limit]

        results = []
        for candidate in paginated:
            results.append(
                {
                    "user": candidate,
                    "mutual_count": candidate.mutual_count,
                    "reason": f"You have {candidate.mutual_count} mutual friend(s) in common",
                }
            )
        return results

    @classmethod
    def get_friend_suggestions(
        cls,
        user: User,
        limit_social: int = 10,
        limit_matches: int = 10,
        offset_social: int = 0,
        offset_matches: int = 0,
        max_distance_km: Optional[float] = None,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
    ) -> Dict[str, List[Dict]]:
        """
        Returns combined suggestions:
        - suggested_by_friends: friends of friends
        - best_matches: algorithm-based matches
        """
        suggested_by_friends = cls.get_suggested_users(
            user, limit=limit_social, offset=offset_social
        )
        best_matches = cls.get_matches(
            user,
            limit=limit_matches,
            offset=offset_matches,
            max_distance_km=max_distance_km,
            min_age=min_age,
            max_age=max_age,
        )
        return {
            "suggested_by_friends": suggested_by_friends,
            "best_matches": best_matches,
        }

    @classmethod
    def get_mutual_friends_count(cls, user1: User, user2: User) -> int:
        """
        Returns the number of users that user1 follows and who also follow user2.
        (Common definition of "mutual friends" in a follow-based system)
        """
        user1_following = set(
            UserFollow.objects.filter(follower=user1).values_list("following_id", flat=True)
        )
        user2_followers = set(
            UserFollow.objects.filter(following=user2).values_list("follower_id", flat=True)
        )
        return len(user1_following.intersection(user2_followers))
    
    @classmethod
    def get_matches_paginated(
        cls,
        user: User,
        limit: int = 20,
        offset: int = 0,
        filters: Optional[Dict[str, any]] = None,
        max_candidates: int = 500,
    ) -> Tuple[List[Dict], int]:
        """
        Returns a paginated list of potential matches and the total number of matches
        that meet the criteria (before pagination).

        Args:
            user: The current user for whom matches are being generated.
            limit: Maximum number of matches to return.
            offset: Number of matches to skip.
            filters: Optional dictionary with keys:
                - max_distance_km (float): Maximum allowed distance in kilometers.
                - min_age (int): Minimum age of the candidate.
                - max_age (int): Maximum age of the candidate.
            max_candidates: Maximum number of candidates to fetch from the database
                        for scoring. Defaults to 500.

        Returns:
            Tuple[List[Dict], int]: A list of match dictionaries (each containing
            'user', 'score', and 'reasons') sliced according to limit/offset, and
            the total number of matches that scored > 0 before pagination.
        """
        if filters is None:
            filters = {}

        max_distance_km = filters.get("max_distance_km")
        min_age = filters.get("min_age")
        max_age = filters.get("max_age")

        # Retrieve all scored matches (up to max_candidates) without pagination
        all_matches = cls.get_matches(
            user=user,
            limit=max_candidates,  # Fetch up to max_candidates, but scoring will stop there
            offset=0,
            max_distance_km=max_distance_km,
            min_age=min_age,
            max_age=max_age,
            max_candidates=max_candidates,
        )

        total = len(all_matches)
        paginated = all_matches[offset : offset + limit]
        return paginated, total