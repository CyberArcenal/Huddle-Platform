# accounts/base.py
from django.urls import path

from users.views.login.OtpRequest import OtpRequestDetailView, OtpRequestListView

urlpatterns = [
    path('', OtpRequestListView.as_view(), name='otp-requests-list'),
    path('<int:id>/', OtpRequestDetailView.as_view(), name='otp-requests-detail'),
]