# search/serializers/content_serializers.py
from typing import Optional

from rest_framework import serializers
from users.models import User
from groups.models import Group
from events.models import Event
from users.services.user_image import UserImageService


class UserSearchSerializer(serializers.ModelSerializer):
    profile_picture = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'profile_picture', 'bio', 'is_verified']
        
    def get_profile_picture(self, obj: User) -> Optional[str]:
        """Get profile picture URL"""
        request = self.context.get("request", None)
        if request:
            return UserImageService.get_active_image_url(image_type="profile", build_url=True, request=request)
        

