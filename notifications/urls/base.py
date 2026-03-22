from django.urls import path

from notifications.views.base import NotificationDetailView, NotificationListView, NotificationMarkAllReadView, NotificationMarkReadView, NotificationUnreadCountView
from notifications.views.email_template import EmailTemplateCRUD
from notifications.views.notify_log import NotifyLogCRUD, NotifyLogResend, NotifyLogRetry

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('<int:pk>/', NotificationDetailView.as_view(), name='notification-detail'),
    path('mark-read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('mark-all-read/', NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
    
    
    # Email Templates
    path('email-templates/', EmailTemplateCRUD.as_view(), name='emailtemplate-list'),
    path('email-templates/<int:id>/', EmailTemplateCRUD.as_view(), name='emailtemplate-detail'),
    

    path("notifylogs/", NotifyLogCRUD.as_view(), name=""),
    path("notifylogs/<int:id>/", NotifyLogCRUD.as_view(), name=""),
    path("notifylogs/<int:id>/retry/", NotifyLogRetry.as_view(), name=""),
    path("notifylogs/<int:id>/resend/", NotifyLogResend.as_view(), name=""),
]

app_name = 'notifications'