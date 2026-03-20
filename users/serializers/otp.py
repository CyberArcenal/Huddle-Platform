from rest_framework import serializers
from django.utils import timezone
import logging

from users.models import OtpRequest, User
from users.models.base import OTP_TYPES
from users.serializers.user import UserMinimalSerializer
from users.services.otp_request import OtpRequestService

logger = logging.getLogger(__name__)


# ------------------ Minimal Serializer (for lists) ------------------
class OtpRequestMinimalSerializer(serializers.ModelSerializer):
    user_data = UserMinimalSerializer(source='user', read_only=True)
    status_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = OtpRequest
        fields = [
            'id',
            'user_data',
            'email',
            'phone',
            'type',
            'created_at',
            'is_used',
            'status_display',
        ]
        read_only_fields = fields

    def get_status_display(self, obj) -> str:
        if obj.is_used:
            return "Used"
        if timezone.now() > obj.expires_at:
            return "Expired"
        return "Active"


# ------------------ Create Serializer (uses service) ------------------


class OtpRequestCreateSerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=True
    )
    type = serializers.ChoiceField(
        choices=OTP_TYPES,
        default='email'
    )

    def validate(self, data):
        if not data.get('user'):
            raise serializers.ValidationError("User must be provided.")
        return data

    def create(self, validated_data):
        user: User = validated_data['user']
        otp_type = validated_data.get('type', 'email')

        # Derive email/phone from user based on type
        email = None
        phone = None
        if otp_type == 'email':
            email = user.email
            if not email:
                raise serializers.ValidationError("User has no email set.")
        elif otp_type == 'phone':
            phone = getattr(user, 'phone', None)
            if not phone:
                raise serializers.ValidationError("User has no phone set.")

        try:
            otp_request = OtpRequestService.create_otp_request(
                user=user,
                email=email,
                phone=phone,
                otp_type=otp_type
                # expiration handled internally by service
            )
            return otp_request
        except Exception as e:
            logger.error(f"OTP creation failed via service: {e}")
            raise serializers.ValidationError(str(e))


# ------------------ Display Serializer (full detail) ------------------
class OtpRequestDisplaySerializer(serializers.ModelSerializer):
    user_data = UserMinimalSerializer(source='user', read_only=True)
    status_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = OtpRequest
        fields = [
            'id',
            'user',
            'user_data',
            'otp_code',
            'email',
            'phone',
            'created_at',
            'expires_at',
            'is_used',
            'attempt_count',
            'type',
            'is_email_delivered',
            'is_phone_delivered',
            'status_display',
        ]
        read_only_fields = [
            'id', 'otp_code', 'created_at', 'expires_at',
            'is_used', 'attempt_count', 'is_email_delivered', 'is_phone_delivered'
        ]

    def get_status_display(self, obj) -> str:
        if obj.is_used:
            return "Used"
        if timezone.now() > obj.expires_at:
            return "Expired"
        return "Active"


# ------------------ Response serializers for drf-spectacular ------------------
class OtpRequestListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = OtpRequestMinimalSerializer(many=True)


class OtpRequestDetailResponseSerializer(serializers.Serializer):
    data = OtpRequestDisplaySerializer()