

import users.services.user_image

import users.models
import rest_framework
import typing
import users.services.user_follow

class HobbySerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = users.models.Hobby
        fields = ["id", "name"]

class UserMinimalSerializer(rest_framework.serializers.ModelSerializer):
    """Minimal serializer for user references (e.g. in followers list)"""

    profile_picture_url = rest_framework.serializers.SerializerMethodField()
    full_name = rest_framework.serializers.SerializerMethodField()
    hobbies = HobbySerializer(many=True, read_only=True)
    capability_score = rest_framework.serializers.IntegerField(required=False)
    reasons = rest_framework.serializers.ListField(child=rest_framework.serializers.CharField(), required=False)
    is_following = rest_framework.serializers.SerializerMethodField()

    class Meta:
        model = users.models.User
        fields = [
            "id",
            "username",
            "profile_picture_url",
            "personality_type",
            "hobbies",
            "full_name",
            "location",
            "capability_score",
            "reasons",
            "is_following",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"required": True, "allow_null": False},
            "username": {"required": True, "allow_null": False},
        }

    def get_is_following(self, obj: users.models.User) -> bool:
        request = self.context.get("request", None)
        if request and request.user.is_authenticated and request.user != obj:
            return users.services.user_follow.UserFollowService.is_following(request.user, obj)
        return False

    def get_profile_picture_url(self, obj: users.models.User) -> typing.Optional[str]:
        try:
            active = users.services.user_image.UserImageService.get_active_image(obj, "profile")
            if active and active.is_active:
                request = self.context.get("request")
                if not request or not request.user.is_authenticated:
                    return (
                        request.build_absolute_uri(active.image.url)
                        if active.privacy == "public"
                        else None
                    )
                if request.user == obj:
                    return request.build_absolute_uri(active.image.url)
                if active.privacy == "public":
                    return request.build_absolute_uri(active.image.url)
                if active.privacy == "followers" and users.services.user_follow.UserFollowService.is_following(
                    request.user, obj
                ):
                    return request.build_absolute_uri(active.image.url)
                return None
            return None
        except:
            # import traceback; traceback.print_exc()
            return None

    def get_full_name(self, obj: users.models.User) -> str:
        """Get full name of the user"""
        if obj.middle_name:
            return f"{obj.first_name} {obj.middle_name} {obj.last_name}".strip()
        else:
            return f"{obj.first_name} {obj.last_name}".strip()

    def to_representation(self, instance):
        """Remove capability_score if not set"""
        data = super().to_representation(instance)
        if data.get("capability_score") is None:
            data.pop("capability_score", None)
        if not data.get("reasons"):
            data.pop("reasons", None)
        return data