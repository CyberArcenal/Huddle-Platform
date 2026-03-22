# services/matching.py
import math
from typing import List, Dict, Optional, Tuple
from django.db.models import Count, Q, Prefetch
from django.utils import timezone
from datetime import date

from users.models.user import User, UserStatus
from users.services.user_follow import UserFollowService


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
        from django.conf import settings
        return getattr(settings, "MATCHING_WEIGHTS", cls.DEFAULT_WEIGHTS)

    @staticmethod
    def calculate_age(birth_date: Optional[date]) -> Optional[int]:
        if not birth_date:
            return None
        today = date.today()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
        if None in (lat1, lon1, lat2, lon2):
            return None
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    @classmethod
    def calculate_match_score(cls, user: User, candidate: User, **kwargs) -> Tuple[int, List[str]]:
        """Return (score, reasons list) for the match between user and candidate."""
        weights = kwargs.get("weights", cls.get_weights())
        max_distance_km = kwargs.get("max_distance_km")
        preferred_age_range = kwargs.get("preferred_age_range")

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
                reasons.append(f"Compatible personality type ({user.personality_type} with {candidate.personality_type}) +{ptc}")

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

        # Overlaps (counts)
        hobby_overlap = user.hobbies.filter(id__in=candidate.hobbies.values_list("id", flat=True)).count()
        if hobby_overlap:
            ho = hobby_overlap * weights.get("hobby_overlap", 1)
            score += ho
            reasons.append(f"{hobby_overlap} common hobbies +{ho}")

        interest_overlap = user.interests.filter(id__in=candidate.interests.values_list("id", flat=True)).count()
        if interest_overlap:
            io = interest_overlap * weights.get("interest_overlap", 1)
            score += io
            reasons.append(f"{interest_overlap} common interests +{io}")

        music_overlap = user.favorite_music.filter(id__in=candidate.favorite_music.values_list("id", flat=True)).count()
        if music_overlap:
            mo = music_overlap * weights.get("music_overlap", 1)
            score += mo
            reasons.append(f"{music_overlap} common music tastes +{mo}")

        cause_overlap = user.causes.filter(id__in=candidate.causes.values_list("id", flat=True)).count()
        if cause_overlap:
            co = cause_overlap * weights.get("cause_overlap", 1)
            score += co
            reasons.append(f"{cause_overlap} common causes +{co}")

        favorite_overlap = user.favorites.filter(id__in=candidate.favorites.values_list("id", flat=True)).count()
        if favorite_overlap:
            fo = favorite_overlap * weights.get("favorite_overlap", 0.5)
            score += fo
            reasons.append(f"{favorite_overlap} common favorites +{fo}")

        work_overlap = user.works.filter(id__in=candidate.works.values_list("id", flat=True)).count()
        if work_overlap:
            wo = work_overlap * weights.get("work_overlap", 0.5)
            score += wo
            reasons.append(f"{work_overlap} common works +{wo}")

        school_overlap = user.schools.filter(id__in=candidate.schools.values_list("id", flat=True)).count()
        if school_overlap:
            so = school_overlap * weights.get("school_overlap", 0.5)
            score += so
            reasons.append(f"{school_overlap} common schools +{so}")

        lifestyle_overlap = user.lifestyle_tags.filter(id__in=candidate.lifestyle_tags.values_list("id", flat=True)).count()
        if lifestyle_overlap:
            lso = lifestyle_overlap * weights.get("lifestyle_tag_overlap", 0.5)
            score += lso
            reasons.append(f"{lifestyle_overlap} common lifestyle tags +{lso}")

        achievement_overlap = user.achievements.filter(id__in=candidate.achievements.values_list("id", flat=True)).count()
        if achievement_overlap:
            ao = achievement_overlap * weights.get("achievement_overlap", 0.5)
            score += ao
            reasons.append(f"{achievement_overlap} common achievements +{ao}")

        # Location
        if max_distance_km is not None and user.latitude and user.longitude and candidate.latitude and candidate.longitude:
            distance = cls.calculate_distance(user.latitude, user.longitude, candidate.latitude, candidate.longitude)
            if distance is not None and distance <= max_distance_km:
                lp = weights.get("location_proximity", 5) * (1 - distance / max_distance_km)
                score += lp
                reasons.append(f"Within {distance:.1f} km +{lp:.1f}")

        # Age
        if preferred_age_range and user.date_of_birth:
            age = cls.calculate_age(user.date_of_birth)
            if age is not None and preferred_age_range[0] <= age <= preferred_age_range[1]:
                am = weights.get("age_match", 3)
                score += am
                reasons.append(f"Within age range ({age} years) +{am}")

        return int(score), reasons

    @classmethod
    def get_matches(
        cls,
        user: User,
        limit: int = 20,
        offset: int = 0,
        filters: Optional[Dict] = None,
        max_candidates: int = 500,
    ) -> List[Dict]:
        """Return a list of dicts with user, score, reasons."""
        if filters is None:
            filters = {}

        qs = User.objects.filter(status=UserStatus.ACTIVE).exclude(id=user.id)

        max_distance_km = filters.get("max_distance_km")
        min_age = filters.get("min_age")
        max_age = filters.get("max_age")

        if min_age is not None or max_age is not None:
            today = date.today()
            if min_age is not None:
                max_birth_date = date(today.year - min_age, today.month, today.day)
                qs = qs.filter(date_of_birth__lte=max_birth_date)
            if max_age is not None:
                min_birth_date = date(today.year - max_age, today.month, today.day)
                qs = qs.filter(date_of_birth__gte=min_birth_date)

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

        prefetch = [
            "hobbies", "interests", "favorites", "favorite_music",
            "works", "schools", "achievements", "causes", "lifestyle_tags"
        ]
        qs = qs.prefetch_related(*prefetch)

        candidates = list(qs[:max_candidates])

        results = []
        for candidate in candidates:
            score, reasons = cls.calculate_match_score(user, candidate, **filters)
            if score > 0:
                candidate.capability_score = score
                results.append({"user": candidate, "score": score, "reasons": reasons})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[offset:offset+limit]

    @classmethod
    def get_suggested_users(
        cls,
        user: User,
        limit: int = 20,
        offset: int = 0,
        min_mutual: int = 1,
    ) -> List[Dict]:
        """
        Suggest users based on friends of friends.
        Returns a list of dicts with user, mutual_count, reason.
        """
        from users.models import UserFollow
        from django.db.models import Count, Q

        following_ids = UserFollow.objects.filter(follower=user).values_list('following_id', flat=True)
        if not following_ids:
            return []

        already_followed_ids = UserFollow.objects.filter(follower=user).values_list('following_id', flat=True)

        candidates_qs = User.objects.filter(
            id__in=UserFollow.objects.filter(
                follower_id__in=following_ids
            ).values_list('following_id', flat=True)
        ).exclude(
            id=user.id
        ).exclude(
            id__in=already_followed_ids
        ).annotate(
            mutual_count=Count(
                'followers',
                filter=Q(followers__follower=user)
            )
        ).filter(mutual_count__gte=min_mutual).order_by('-mutual_count')

        candidates_qs = candidates_qs.prefetch_related(
            "hobbies", "interests", "favorites", "favorite_music",
            "works", "schools", "achievements", "causes", "lifestyle_tags"
        )

        paginated = candidates_qs[offset:offset+limit]

        results = []
        for candidate in paginated:
            results.append({
                "user": candidate,
                "mutual_count": candidate.mutual_count,
                "reason": f"You have {candidate.mutual_count} mutual friend(s) in common"
            })
        return results

    @classmethod
    def get_friend_suggestions(
        cls,
        user: User,
        limit_social: int = 10,
        limit_matches: int = 10,
        offset_social: int = 0,
        offset_matches: int = 0,
        match_filters: Optional[Dict] = None,
    ) -> Dict[str, List[Dict]]:
        """Return combined suggestions."""
        suggested_by_friends = cls.get_suggested_users(
            user, limit=limit_social, offset=offset_social
        )
        best_matches = cls.get_matches(
            user, limit=limit_matches, offset=offset_matches, filters=match_filters
        )
        return {
            "suggested_by_friends": suggested_by_friends,
            "best_matches": best_matches,
        }

    @classmethod
    def get_mutual_friends_count(cls, user1: User, user2: User) -> int:
        from users.models import UserFollow
        user1_following = set(UserFollow.objects.filter(follower=user1).values_list('following_id', flat=True))
        user2_followers = set(UserFollow.objects.filter(following=user2).values_list('follower_id', flat=True))
        return len(user1_following.intersection(user2_followers))