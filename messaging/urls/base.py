from django.urls import path

from messaging.views import conversation, mark_read, message

urlpatterns = [
    # Conversations
    path('conversations/', conversation.ConversationListView.as_view(), name='conversation-list'),
    path('conversations/<int:pk>/', conversation.ConversationDetailView.as_view(), name='conversation-detail'),

    # Messages in a conversation
    path('conversations/<int:conversation_pk>/messages/', message.MessageListView.as_view(), name='message-list'),

    # Mark messages as read
    path('conversations/<int:conversation_pk>/mark-read/', mark_read.MarkMessagesReadView.as_view(), name='mark-read'),
]

app_name = 'messaging'