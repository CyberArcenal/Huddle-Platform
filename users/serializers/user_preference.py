from rest_framework import serializers
from drf_spectacular.utils import extend_schema

from users.models import (
    Hobby, Interest, Favorite, Music, Work, School,
    Achievement, SocialCause, LifestyleTag
)
from users.serializers.user.base import (
    HobbySerializer, InterestSerializer, FavoriteSerializer,
    MusicSerializer, WorkSerializer, SchoolSerializer,
    AchievementSerializer, SocialCauseSerializer, LifestyleTagSerializer
)
from users.views.user_preferences import BaseUserPreferenceView



def make_preference_response_serializer(child_serializer_class):
    """
    Creates a serializer class for response:
        { "available": [ ... ], "selected": [ ... ] }
    """
    class UserPreferenceResponseSerializer(serializers.Serializer):
        available = serializers.ListField(child=child_serializer_class())
        selected = serializers.ListField(child=child_serializer_class())
    return UserPreferenceResponseSerializer


def make_preference_request_serializer():
    """
    Creates a serializer class for request:
        { "ids": [1, 2, 3] }
    """
    class UserPreferenceRequestSerializer(serializers.Serializer):
        ids = serializers.ListField(child=serializers.IntegerField(), required=True)
    return UserPreferenceRequestSerializer


# ---------- Hobbies ----------
class UserHobbiesView(BaseUserPreferenceView):
    model_class = Hobby
    serializer_class = HobbySerializer
    relation_name = 'hobbies'

    @extend_schema(
        summary="Get available and selected hobbies",
        responses={200: make_preference_response_serializer(HobbySerializer)},
        tags=["User Preferences"]
    )
    def get(self, request):
        return super().get(request)

    @extend_schema(
        summary="Update user's selected hobbies",
        request=make_preference_request_serializer(),
        responses={200: make_preference_response_serializer(HobbySerializer)},
        tags=["User Preferences"]
    )
    def put(self, request):
        return super().put(request)


# ---------- Interests ----------
class UserInterestsView(BaseUserPreferenceView):
    model_class = Interest
    serializer_class = InterestSerializer
    relation_name = 'interests'

    @extend_schema(
        summary="Get available and selected interests",
        responses={200: make_preference_response_serializer(InterestSerializer)},
        tags=["User Preferences"]
    )
    def get(self, request):
        return super().get(request)

    @extend_schema(
        summary="Update user's selected interests",
        request=make_preference_request_serializer(),
        responses={200: make_preference_response_serializer(InterestSerializer)},
        tags=["User Preferences"]
    )
    def put(self, request):
        return super().put(request)


# ---------- Favorites ----------
class UserFavoritesView(BaseUserPreferenceView):
    model_class = Favorite
    serializer_class = FavoriteSerializer
    relation_name = 'favorites'

    @extend_schema(
        summary="Get available and selected favorites",
        responses={200: make_preference_response_serializer(FavoriteSerializer)},
        tags=["User Preferences"]
    )
    def get(self, request):
        return super().get(request)

    @extend_schema(
        summary="Update user's selected favorites",
        request=make_preference_request_serializer(),
        responses={200: make_preference_response_serializer(FavoriteSerializer)},
        tags=["User Preferences"]
    )
    def put(self, request):
        return super().put(request)


# ---------- Music ----------
class UserMusicView(BaseUserPreferenceView):
    model_class = Music
    serializer_class = MusicSerializer
    relation_name = 'favorite_music'

    @extend_schema(
        summary="Get available and selected music preferences",
        responses={200: make_preference_response_serializer(MusicSerializer)},
        tags=["User Preferences"]
    )
    def get(self, request):
        return super().get(request)

    @extend_schema(
        summary="Update user's selected music preferences",
        request=make_preference_request_serializer(),
        responses={200: make_preference_response_serializer(MusicSerializer)},
        tags=["User Preferences"]
    )
    def put(self, request):
        return super().put(request)


# ---------- Works ----------
class UserWorksView(BaseUserPreferenceView):
    model_class = Work
    serializer_class = WorkSerializer
    relation_name = 'works'

    @extend_schema(
        summary="Get available and selected works",
        responses={200: make_preference_response_serializer(WorkSerializer)},
        tags=["User Preferences"]
    )
    def get(self, request):
        return super().get(request)

    @extend_schema(
        summary="Update user's selected works",
        request=make_preference_request_serializer(),
        responses={200: make_preference_response_serializer(WorkSerializer)},
        tags=["User Preferences"]
    )
    def put(self, request):
        return super().put(request)


# ---------- Schools ----------
class UserSchoolsView(BaseUserPreferenceView):
    model_class = School
    serializer_class = SchoolSerializer
    relation_name = 'schools'

    @extend_schema(
        summary="Get available and selected schools",
        responses={200: make_preference_response_serializer(SchoolSerializer)},
        tags=["User Preferences"]
    )
    def get(self, request):
        return super().get(request)

    @extend_schema(
        summary="Update user's selected schools",
        request=make_preference_request_serializer(),
        responses={200: make_preference_response_serializer(SchoolSerializer)},
        tags=["User Preferences"]
    )
    def put(self, request):
        return super().put(request)


# ---------- Achievements ----------
class UserAchievementsView(BaseUserPreferenceView):
    model_class = Achievement
    serializer_class = AchievementSerializer
    relation_name = 'achievements'

    @extend_schema(
        summary="Get available and selected achievements",
        responses={200: make_preference_response_serializer(AchievementSerializer)},
        tags=["User Preferences"]
    )
    def get(self, request):
        return super().get(request)

    @extend_schema(
        summary="Update user's selected achievements",
        request=make_preference_request_serializer(),
        responses={200: make_preference_response_serializer(AchievementSerializer)},
        tags=["User Preferences"]
    )
    def put(self, request):
        return super().put(request)


# ---------- Social Causes ----------
class UserCausesView(BaseUserPreferenceView):
    model_class = SocialCause
    serializer_class = SocialCauseSerializer
    relation_name = 'causes'

    @extend_schema(
        summary="Get available and selected social causes",
        responses={200: make_preference_response_serializer(SocialCauseSerializer)},
        tags=["User Preferences"]
    )
    def get(self, request):
        return super().get(request)

    @extend_schema(
        summary="Update user's selected social causes",
        request=make_preference_request_serializer(),
        responses={200: make_preference_response_serializer(SocialCauseSerializer)},
        tags=["User Preferences"]
    )
    def put(self, request):
        return super().put(request)


# ---------- Lifestyle Tags ----------
class UserLifestyleTagsView(BaseUserPreferenceView):
    model_class = LifestyleTag
    serializer_class = LifestyleTagSerializer
    relation_name = 'lifestyle_tags'

    @extend_schema(
        summary="Get available and selected lifestyle tags",
        responses={200: make_preference_response_serializer(LifestyleTagSerializer)},
        tags=["User Preferences"]
    )
    def get(self, request):
        return super().get(request)

    @extend_schema(
        summary="Update user's selected lifestyle tags",
        request=make_preference_request_serializer(),
        responses={200: make_preference_response_serializer(LifestyleTagSerializer)},
        tags=["User Preferences"]
    )
    def put(self, request):
        return super().put(request)