# users/services/personality_quiz.py

from collections import defaultdict
from users.models import PersonalityQuestion, PersonalityResponse, PersonalityAssessmentSession
from users.enums import UserStatus  # or wherever your MBTIType is defined
from django.utils import timezone
PERSONALITY_TYPE_DETAILS = {
    'INTJ': {
        'name': 'The Architect',
        'description': 'Strategic thinkers with a plan for everything. They value knowledge and competence.',
        'strengths': ['Strategic', 'Confident', 'Hardworking', 'Open-minded', 'Determined'],
        'weaknesses': ['Arrogant', 'Judgmental', 'Overly analytical', 'Loathe highly structured environments'],
        'career_matches': ['Scientist', 'Engineer', 'Professor', 'Lawyer', 'Strategist'],
        'relationship_advice': 'Appreciate their need for intellectual stimulation. Give them space to work on their ideas.',
    },
    'INTP': {
        'name': 'The Logician',
        'description': 'Innovative inventors with an unquenchable thirst for knowledge.',
        'strengths': ['Analytical', 'Original', 'Open-minded', 'Curious', 'Objective'],
        'weaknesses': ['Disconnected', 'Absent-minded', 'Condescending', 'Loathe rules'],
        'career_matches': ['Software Developer', 'Philosopher', 'Mathematician', 'Architect'],
        'relationship_advice': 'Engage in deep conversations. Respect their need for alone time.',
    },
    'ENTJ': {
        'name': 'The Commander',
        'description': 'Bold, imaginative, and strong-willed leaders, always finding a way.',
        'strengths': ['Efficient', 'Energetic', 'Self-confident', 'Strategic', 'Charismatic'],
        'weaknesses': ['Stubborn', 'Intolerant', 'Impatient', 'Arrogant', 'Poor handling of emotions'],
        'career_matches': ['Executive', 'Entrepreneur', 'Lawyer', 'Project Manager'],
        'relationship_advice': 'Show appreciation for their drive. Be direct and honest.',
    },
    'ENTP': {
        'name': 'The Debater',
        'description': 'Smart and curious thinkers who cannot resist an intellectual challenge.',
        'strengths': ['Knowledgeable', 'Quick-thinking', 'Original', 'Excellent brainstormers'],
        'weaknesses': ['Argumentative', 'Insensitive', 'Intolerant', 'Disorganized'],
        'career_matches': ['Lawyer', 'Marketing', 'Actor', 'Engineer', 'Inventor'],
        'relationship_advice': 'Engage in friendly debates. Allow them to explore new ideas.',
    },
    # Add all 16 types... (abbreviated for brevity)
    # You should complete this dictionary with all MBTI types.
}

def get_personality_details(mbti_type):
    return PERSONALITY_TYPE_DETAILS.get(mbti_type, {
        'name': 'Unknown',
        'description': 'Complete the quiz to discover your personality type.',
        'strengths': [],
        'weaknesses': [],
        'career_matches': [],
        'relationship_advice': '',
    })
    
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
            # Convert 1-5 scale to -2 to +2 (centered at 3)
            value = resp.answer - 3  # -2 (disagree) to +2 (agree)
            
            if q.direction:
                # Agree adds to first trait
                first_trait = q.dimension[0]   # E, S, T, J
                scores[q.dimension][first_trait] += value
                # Disagree adds to second trait (implicitly)
                second_trait = q.dimension[1]   # I, N, F, P
                scores[q.dimension][second_trait] -= value
            else:
                # Agree adds to second trait
                first_trait = q.dimension[0]
                second_trait = q.dimension[1]
                scores[q.dimension][first_trait] -= value
                scores[q.dimension][second_trait] += value
        
        # Determine letter for each dimension
        result = ''
        for dim, traits in scores.items():
            if traits[dim[0]] >= traits[dim[1]]:
                result += dim[0]
            else:
                result += dim[1]
        
        return result  # e.g., 'INTJ'
    
    @classmethod
    def save_assessment_result(cls, user, result_type, score_details=None):
        """Save the computed personality type to user profile"""
        user.personality_type = result_type
        user.save(update_fields=['personality_type'])
        
        # Close the current session
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
            details = get_personality_details(result)
            return {
                'personality_type': result,
                'details': details
            }
        return {
            'personality_type': None,
            'details': None
        }