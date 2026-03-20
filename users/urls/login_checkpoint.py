# accounts/base.py
from django.urls import path

from users.views.login.login_checkpoint import LoginCheckpointDetailView, LoginCheckpointListView


urlpatterns = [
    path('', LoginCheckpointListView.as_view(), name='-list'),
    path('<int:id>/', LoginCheckpointDetailView.as_view(), name='-detail'),
]