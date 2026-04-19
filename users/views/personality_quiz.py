# users/views/personality_quiz.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from users.services.personality_quiz import PersonalityQuizService
from users.models import PersonalityQuestion, PersonalityAssessmentSession
from rest_framework.permissions import IsAuthenticated

class PersonalityQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalityQuestion
        fields = ['id', 'text', 'dimension', 'order']

class SubmitAnswerSerializer(serializers.Serializer):
    answers = serializers.DictField(
        child=serializers.IntegerField(min_value=1, max_value=5),
        help_text="Map of question_id -> answer (1-5)"
    )
    
class PersonalityDetailsSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    strengths = serializers.ListField(child=serializers.CharField())
    weaknesses = serializers.ListField(child=serializers.CharField())
    career_matches = serializers.ListField(child=serializers.CharField())
    relationship_advice = serializers.CharField()
    compatible_types = serializers.ListField(child=serializers.CharField())
    
class PersonalityTypeResponseDataSerializer(serializers.Serializer):
    personality_type = serializers.CharField(allow_null=True)
    completed = serializers.BooleanField()
    progress = serializers.FloatField()  # 0.0 to 1.0
    details = PersonalityDetailsSerializer()  # name, description, etc. of the personality type
    
class PersonalityTypeResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PersonalityTypeResponseDataSerializer()


class PersonalityQuizQuestionResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PersonalityQuestionSerializer(many=True)
    
class PersonalityQuizQuestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    @extend_schema(
        tags=["Personality Quiz"],
        responses={200: PersonalityQuizQuestionResponseSerializer},
        description="Get all active personality quiz questions."
    )
    def get(self, request):
        questions = PersonalityQuizService.get_all_questions()
        serializer = PersonalityQuestionSerializer(questions, many=True)
        return Response({
            "status": True,
            "message": "Questions retrieved",
            "data": serializer.data
        })

class PersonalityQuizSubmitView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    @extend_schema(
        tags=["Personality Quiz"],
        request=SubmitAnswerSerializer,
        responses={200: PersonalityTypeResponseSerializer},
        description="Submit answers and get computed personality type."
    )
    @transaction.atomic
    def post(self, request):
        serializer = SubmitAnswerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": False, "message": "Validation error", "data": serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        answers = {int(k): v for k, v in serializer.validated_data['answers'].items()}
        result_data = PersonalityQuizService.submit_answers(request.user, answers)

        total_questions = PersonalityQuizService.get_all_questions().count()
        answered_count = request.user.personality_responses.count()
        progress = answered_count / total_questions if total_questions > 0 else 0
        
        return Response({
            "status": True,
            "message": "Answers saved",
            "data": {
                "personality_type": result_data['personality_type'],
                "completed": result_data['personality_type'] is not None,
                "progress": progress,
                "details": result_data['details']   # includes name, description, etc.
            }
        })

class PersonalityTypeDetailsView(APIView):
    permission_classes = [IsAuthenticated]  # or IsAuthenticated
    
    class PersonalityTypeDetailsResponseSerializer(serializers.Serializer):
        status = serializers.BooleanField()
        message = serializers.CharField()
        data = PersonalityDetailsSerializer()
        
    @extend_schema(
        tags=["Personality Quiz"],
        parameters=[
             OpenApiParameter(name="mbti_type",type=str, required=True, description="MBTI type (e.g. INFP, ESTJ)")
        ],
        responses={200: PersonalityTypeDetailsResponseSerializer},
        description="Get details about a specific personality type."
    )

    def get(self, request, mbti_type):
        try:
            details = PersonalityQuizService.get_personality_details(mbti_type.upper())
            return Response({"status": True,"message": "Details retrieved", "data": details})
        except Exception as e:
            return Response({"status": False, "message": "Failed to retrieve details", "data": None}, status=status.HTTP_400_BAD_REQUEST)

class PersonalityQuizStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    @extend_schema(
        tags=["Personality Quiz"],
        responses={200: PersonalityTypeResponseSerializer},
        description="Get current user's quiz progress and personality type."
    )
    def get(self, request):
        total_questions = PersonalityQuizService.get_all_questions().count()
        answered_count = request.user.personality_responses.count()
        progress = answered_count / total_questions if total_questions > 0 else 0
        
        return Response({
            "status": True,
            "message": "Status retrieved",
            "data": {
                "personality_type": request.user.personality_type,
                "completed": request.user.personality_type is not None,
                "progress": progress
            }
        })