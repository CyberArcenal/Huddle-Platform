import django.conf
import django.db


class Conversation(django.db.models.Model):
    CONVERSATION_TYPES: list[tuple[str, str]] = [
        ('direct', 'Direct Message'),
        ('group', 'Group Chat'),
    ]
    
    name = django.db.models.CharField(max_length=100, blank=True, null=True)
    conversation_type = django.db.models.CharField(max_length=10, choices=CONVERSATION_TYPES, default='direct')
    participants = django.db.models.ManyToManyField(django.conf.settings.AUTH_USER_MODEL, related_name='conversations')
    created_at = django.db.models.DateTimeField(auto_now_add=True)
    updated_at = django.db.models.DateTimeField(auto_now=True)

    class Meta:
        db_table: str = 'conversations'

