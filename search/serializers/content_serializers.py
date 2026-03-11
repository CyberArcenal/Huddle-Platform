# search/serializers/content_serializers.py
from typing import Optional

from rest_framework import serializers
from users.models import User
from groups.models import Group
from events.models import Event
from feed.models.base import Post


class UserSearchSerializer(serializers.ModelSerializer):
    profile_picture = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'profile_picture', 'bio', 'is_verified']
        
    def get_profile_picture(self, obj: User) -> Optional[str]:
        """Get profile picture URL"""
        if obj.profile_picture:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None

