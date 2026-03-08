from rest_framework import serializers
from users.serializers.user import UserProfileSerializer, UserMinimalSerializer

class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class LoginResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    user = UserProfileSerializer()
    refreshToken = serializers.CharField()
    accessToken = serializers.CharField()
    expiresIn = serializers.IntegerField()
    message = serializers.CharField()

class Login2FARequiredSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    requires_2fa = serializers.BooleanField()
    checkpoint_token = serializers.CharField()
    message = serializers.CharField()
    expires_in = serializers.IntegerField()

class Verify2FARequestSerializer(serializers.Serializer):
    checkpoint_token = serializers.CharField()
    otp_code = serializers.CharField(max_length=6)

class Verify2FAResponseSerializer(LoginResponseSerializer):
    pass

class Resend2FARequestSerializer(serializers.Serializer):
    checkpoint_token = serializers.CharField()

class Resend2FAResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    expires_in = serializers.IntegerField()

class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()

class LogoutResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()

class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()

class TokenRefreshResponseSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    access = serializers.CharField()
    message = serializers.CharField()

class TokenVerifyRequestSerializer(serializers.Serializer):
    token = serializers.CharField()

class TokenVerifyResponseSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    user = UserMinimalSerializer()

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

class PasswordResetRequestResponseSerializer(serializers.Serializer):
    message = serializers.CharField()

class PasswordResetVerifyRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6)

class PasswordResetVerifyResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    email = serializers.EmailField()
    verified = serializers.BooleanField()
    checkpoint_token = serializers.CharField()

class PasswordResetCompleteRequestSerializer(serializers.Serializer):
    checkpoint_token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

class PasswordResetCompleteResponseSerializer(serializers.Serializer):
    message = serializers.CharField()

class PasswordChangeRequestSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

class PasswordChangeResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    changed_at = serializers.DateTimeField()

class PasswordStrengthCheckRequestSerializer(serializers.Serializer):
    password = serializers.CharField()

class PasswordStrengthCheckResponseSerializer(serializers.Serializer):
    strength_score = serializers.IntegerField()
    strength_level = serializers.CharField()
    is_acceptable = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    suggestions = serializers.ListField(child=serializers.CharField())

class PasswordHistoryResponseSerializer(serializers.Serializer):
    total_events = serializers.IntegerField()
    events = serializers.ListField(child=serializers.DictField())