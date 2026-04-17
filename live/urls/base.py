from django.urls import path
from live.views.live import (
    LiveTokenView, StartLiveView, EndLiveView, ActiveLivesView, LiveDetailView,
    RequestJoinLiveView, RespondToJoinRequestView, LiveParticipantsView,
    LeaveLiveView, PendingRequestsView
)
from live.views.webhook import livekit_webhook

urlpatterns = [
    path('start/', StartLiveView.as_view(), name='live-start'),
    path('<int:live_id>/end/', EndLiveView.as_view(), name='live-end'),
    path('active/', ActiveLivesView.as_view(), name='live-active'),
    path('<int:live_id>/', LiveDetailView.as_view(), name='live-detail'),
    path('<int:live_id>/request/', RequestJoinLiveView.as_view(), name='live-request'),
    path('requests/<int:request_id>/respond/', RespondToJoinRequestView.as_view(), name='live-respond'),
    path('<int:live_id>/participants/', LiveParticipantsView.as_view(), name='live-participants'),
    path('<int:live_id>/leave/', LeaveLiveView.as_view(), name='live-leave'),
    path('<int:live_id>/pending-requests/', PendingRequestsView.as_view(), name='live-pending'),
    path('<int:live_id>/token/', LiveTokenView.as_view(), name='live-token'),
    path('webhook/', livekit_webhook, name='livekit-webhook'),
]