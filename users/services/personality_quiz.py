# users/services/personality_quiz.py

from collections import defaultdict
from django.core.cache import cache
from users.models import PersonalityQuestion, PersonalityResponse, PersonalityAssessmentSession, PersonalityTypeDetail
from django.utils import timezone

class PersonalityQuizService:
    
    DIMENSION_SCORES = {
        'EI': {'E': 0, 'I': 0},
        'SN': {'S': 0, 'N': 0},
        'TF': {'T': 0, 'F': 0},
        'JP': {'J': 0, 'P': 0},
    }
    
    @classmethod
    def get_all_questions(cls):
        return PersonalityQuestion.objects.filter(is_active=True).order_by('order')
    
    @classmethod
    def compute_personality_type(cls, user):
        """Compute MBTI type based on user's answers"""
        responses = PersonalityResponse.objects.filter(user=user).select_related('question')
        if responses.count() < cls.get_all_questions().count():
            return None  # Not enough answers
        
        scores = defaultdict(lambda: defaultdict(int))
        
        for resp in responses:
            q = resp.question
            value = resp.answer - 3  # -2 (disagree) to +2 (agree)
            
            if q.direction:
                first_trait = q.dimension[0]   # E, S, T, J
                scores[q.dimension][first_trait] += value
                second_trait = q.dimension[1]   # I, N, F, P
                scores[q.dimension][second_trait] -= value
            else:
                first_trait = q.dimension[0]
                second_trait = q.dimension[1]
                scores[q.dimension][first_trait] -= value
                scores[q.dimension][second_trait] += value
        
        result = ''
        for dim, traits in scores.items():
            if traits[dim[0]] >= traits[dim[1]]:
                result += dim[0]
            else:
                result += dim[1]
        
        return result
    
    @classmethod
    def get_personality_details(cls, mbti_type):
        """Fetch personality details from database (with caching)"""
        if not mbti_type:
            return None
        
        cache_key = f"personality_details_{mbti_type}"
        details = cache.get(cache_key)
        
        if details is None:
            try:
                obj = PersonalityTypeDetail.objects.get(mbti_type=mbti_type)
                details = {
                    'name': obj.name,
                    'description': obj.description,
                    'strengths': obj.strengths,
                    'weaknesses': obj.weaknesses,
                    'career_matches': obj.career_matches,
                    'relationship_advice': obj.relationship_advice,
                    'fun_facts': obj.fun_facts,
                    'famous_people': obj.famous_people,
                    'compatible_types': obj.compatible_types
                }
                cache.set(cache_key, details, timeout=3600)  # Cache for 1 hour
            except PersonalityTypeDetail.DoesNotExist:
                details = {
                    'name': 'Unknown',
                    'description': 'Complete the quiz to discover your personality type.',
                    'strengths': [],
                    'weaknesses': [],
                    'career_matches': [],
                    'relationship_advice': '',
                    'fun_facts': [],
                    'famous_people': [],
                    'compatible_types': []
                }
                cache.set(cache_key, details, timeout=300)  # Shorter cache for missing
        
        return details
    
    @classmethod
    def save_assessment_result(cls, user, result_type, score_details=None):
        """Save the computed personality type to user profile"""
        user.personality_type = result_type
        user.save(update_fields=['personality_type'])
        
        session = PersonalityAssessmentSession.objects.filter(
            user=user, completed_at__isnull=True
        ).first()
        if session:
            session.completed_at = timezone.now()
            session.result_type = result_type
            session.score_details = score_details or {}
            session.save()
    
    @classmethod
    def submit_answers(cls, user, answers: dict):
        for q_id, answer_value in answers.items():
            PersonalityResponse.objects.update_or_create(
                user=user,
                question_id=q_id,
                defaults={'answer': answer_value}
            )
        result = cls.compute_personality_type(user)
        if result:
            cls.save_assessment_result(user, result)
            details = cls.get_personality_details(result)
            return {
                'personality_type': result,
                'details': details
            }
        return {
            'personality_type': None,
            'details': None
        }
    
    @classmethod
    def refresh_personality_details_cache(cls, mbti_type=None):
        """Clear cache for one or all personality types"""
        if mbti_type:
            cache.delete(f"personality_details_{mbti_type}")
        else:
            # Clear all MBTI cache keys
            for mbti in dict(PersonalityTypeDetail.MBTI_CHOICES).keys():
                cache.delete(f"personality_details_{mbti}")