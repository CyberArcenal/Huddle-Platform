from django.urls import path

from notifications.views.base import NotificationDetailView, NotificationListView, NotificationMarkAllReadView, NotificationMarkReadView, NotificationUnreadCountView

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('<int:pk>/', NotificationDetailView.as_view(), name='notification-detail'),
    path('mark-read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('mark-all-read/', NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
]

app_name = 'notifications'