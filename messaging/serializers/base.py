from typing import Optional

from rest_framework import serializers
from messaging.models import Conversation, Message
from users.serializers.user import UserMinimalSerializer


class MessageSerializer(serializers.ModelSerializer):
    sender_details = UserMinimalSerializer(source='sender', read_only=True)
    media_url = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'sender_details', 'content',
                  'media', 'media_url', 'media_type', 'is_read', 'is_deleted', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_media_url(self, obj) -> str:
        if obj.media:
            return obj.media.url
        return None


class ConversationSerializer(serializers.ModelSerializer):
    participants_details = UserMinimalSerializer(source='participants', many=True, read_only=True)
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'name', 'conversation_type', 'participants',
                  'participants_details', 'last_message', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_last_message(self, obj) -> Optional[MessageSerializer]:
        last_msg = obj.messages.filter(is_deleted=False).order_by('-created_at').first()
        if last_msg:
            return MessageSerializer(last_msg).data
        return None


class ConversationCreateSerializer(serializers.ModelSerializer):
    participant_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True
    )

    class Meta:
        model = Conversation
        fields = ['name', 'conversation_type', 'participant_ids']

    def create(self, validated_data):
        participant_ids = validated_data.pop('participant_ids')
        # Add the current user automatically
        user = self.context['request'].user
        if user.id not in participant_ids:
            participant_ids.append(user.id)

        conversation = Conversation.objects.create(**validated_data)
        conversation.participants.set(participant_ids)
        return conversation


class MessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['conversation', 'content', 'media', 'media_type']

    def create(self, validated_data):
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)