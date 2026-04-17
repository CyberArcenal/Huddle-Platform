# users/models/personality_quiz.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import User

class PersonalityQuestion(models.Model):
    """Question for personality assessment (e.g., MBTI)"""
    
    # MBTI dimensions: EI, SN, TF, JP
    DIMENSION_CHOICES = [
        ('EI', 'Extraversion (E) vs Introversion (I)'),
        ('SN', 'Sensing (S) vs Intuition (N)'),
        ('TF', 'Thinking (T) vs Feeling (F)'),
        ('JP', 'Judging (J) vs Perceiving (P)'),
    ]
    
    text = models.TextField()
    dimension = models.CharField(max_length=2, choices=DIMENSION_CHOICES)
    # Direction: if True, answer "Agree" adds to first trait (E/S/T/J);
    # if False, adds to second trait (I/N/F/P)
    direction = models.BooleanField(default=True, help_text="True = Agree increases first trait")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.dimension}: {self.text[:50]}"


class PersonalityResponse(models.Model):
    """User's answer to a personality question"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personality_responses')
    question = models.ForeignKey(PersonalityQuestion, on_delete=models.CASCADE)
    answer = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])  # 1=Strongly Disagree, 5=Strongly Agree
    answered_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'question']


class PersonalityAssessmentSession(models.Model):
    """Track when a user takes the assessment"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personality_sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    result_type = models.CharField(max_length=4, null=True, blank=True)  # e.g., 'INTJ'
    score_details = models.JSONField(default=dict)  # Store raw scores per dimension