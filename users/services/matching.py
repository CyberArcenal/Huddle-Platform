from users.models.user import User


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

class MatchingService:
    @staticmethod
    def calculate_match_score(user: User, candidate: User) -> int:
        score = 0

        # Personality compatibility
        if user.personality_type and candidate.personality_type:
            if user.personality_type == candidate.personality_type:
                score += 1  # same type, but lower weight
            elif candidate.personality_type in MBTI_COMPATIBILITY.get(user.personality_type, []):
                score += 3  # complementary type, higher weight

        # Love language
        if user.love_language and user.love_language == candidate.love_language:
            score += 2

        # Relationship goal
        if user.relationship_goal and user.relationship_goal == candidate.relationship_goal:
            score += 2

        # Lifestyle overlaps
        score += user.hobbies.filter(id__in=candidate.hobbies.values_list("id", flat=True)).count()
        score += user.interests.filter(id__in=candidate.interests.values_list("id", flat=True)).count()
        score += user.favorite_music.filter(id__in=candidate.favorite_music.values_list("id", flat=True)).count()
        score += user.causes.filter(id__in=candidate.causes.values_list("id", flat=True)).count()

        return score