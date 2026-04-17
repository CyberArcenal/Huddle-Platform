# dating/urls/base.py
from django.urls import path

from dating.views.dating_message import DatingMessageConversationView, DatingMessageInboxView, DatingMessageMarkReadView, DatingMessageSendView, DatingMessageSentView
from dating.views.dating_preference import DatingPreferenceCompatibilityView, DatingPreferenceView
from dating.views.match import ActiveMatchesListView, MatchCreateView, MatchDetailView, MatchUnmatchView, UserMatchScoresView


urlpatterns = [
    path('', UserMatchScoresView.as_view(), name='match-scores'),
    path('active/', ActiveMatchesListView.as_view(), name='active-matches'),
    path('create/', MatchCreateView.as_view(), name='match-create'),
    path('unmatch/', MatchUnmatchView.as_view(), name='match-unmatch'),
    path('<int:pk>/', MatchDetailView.as_view(), name='match-detail'),
    
    
    path('dating-preferences/', DatingPreferenceView.as_view(), name='dating-preferences'),
    path('dating-preferences/check-compatibility/', DatingPreferenceCompatibilityView.as_view(), name='check-compatibility'),
    
    
    
    path('messages/send/', DatingMessageSendView.as_view(), name='message-send'),
    path('messages/inbox/', DatingMessageInboxView.as_view(), name='message-inbox'),
    path('messages/sent/', DatingMessageSentView.as_view(), name='message-sent'),
    path('messages/conversation/<int:user_id>/', DatingMessageConversationView.as_view(), name='message-conversation'),
    path('messages/<int:pk>/mark-read/', DatingMessageMarkReadView.as_view(), name='message-mark-read'),
]