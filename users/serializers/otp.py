from rest_framework import serializers
from django.utils import timezone
import logging
from django.contrib.auth import get_user_model

from users.models.base import OtpRequest
from users.serializers.user import UserMinimalSerializer

User = get_user_model()


logger = logging.getLogger(__name__)



class OtpRequestSerializer(serializers.ModelSerializer):
    # Nested serializers for read operations
    user_data = UserMinimalSerializer(source='user', read_only=True)
    
    # Display fields for read operations
    status_display = serializers.SerializerMethodField(read_only=True)
    
    # Conditional fields for write operations
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), 
        write_only=True, 
        required=False,
        allow_null=True
    )
    
    email = serializers.EmailField(required=False, allow_null=True)
    
    class Meta:
        model = OtpRequest
        fields = [
            "id",
            "user",
            "user_data",
            "otp_code",
            "email",
            "created_at",
            "expires_at",
            "is_used",
            "attempt_count",
            "status_display"
        ]
        read_only_fields = [
            "id",
            "created_at",
            "expires_at",
            "is_used",
            "attempt_count"
        ]
    
    def get_status_display(self, obj):
        if obj.is_used:
            return "Used"
        elif timezone.now() > obj.expires_at:
            return "Expired"
        else:
            return "Active"
    
    def validate(self, data):
        # Ensure either user or email is provided
        user = data.get('user')
        email = data.get('email')
        
        if not user and not email:
            raise serializers.ValidationError(
                "Either user or email must be provided."
            )
        
        # If user is provided, use their email if email is not explicitly provided
        if user and not email:
            data['email'] = user.email
        
        return data
    
    def create(self, validated_data):
        try:
            # Set expiration time (assuming 10 minutes from creation)
            validated_data['expires_at'] = timezone.now() + timezone.timedelta(minutes=10)
            
            otp_request = OtpRequest.objects.create(**validated_data)
            logger.info(f"OTP request created for {otp_request.email}")
            return otp_request
        except Exception as e:
            logger.error(f"OTP request creation failed: {str(e)}")
            raise serializers.ValidationError(
                {"non_field_errors": [f"Creation failed: {str(e)}"]}
            )
    
    def to_representation(self, instance):
        """Customize output for read operations"""
        representation = super().to_representation(instance)
        
        # For read operations, remove write-only fields
        request = self.context.get("request")
        if request and request.method in ["GET", "HEAD", "OPTIONS"]:
            representation.pop("user", None)
        
        return representation
# ```

# ## Example Usage:
# /api/v1/accounts/otp-requests/
# /api/v1/accounts/otp-requests/<int:id>/
# /api/v1/accounts/otp-requests/<int:id>/<slug:option>/
# **Create OTP Request (POST):**
# ```json
# {
#   "user": 1,
#   "otp_code": "123456"
# }
# ```

# OR

# ```json
# {
#   "email": "user@example.com",
#   "otp_code": "123456"
# }
# ```

# **Get OTP Request (GET) Response:**
# ```json
# {
#   "id": 1,
#   "user_data": {
#     "id": 1,
#     "full_name": "John Doe",
#     "username": "johndoe",
#     "email": "john@example.com",
#     "first_name": "John",
#     "last_name": "Doe"
#   },
#   "otp_code": "123456",
#   "email": "john@example.com",
#   "created_at": "2023-01-01T12:00:00Z",
#   "expires_at": "2023-01-01T12:10:00Z",
#   "is_used": false,
#   "attempt_count": 0,
#   "status_display": "Active"
# }
# ```

# This serializer follows the same pattern as your UserSerializer with:
# - Nested data for related objects in read operations
# - Separate fields for write operations (using primary keys)
# - Custom display fields for status information
# - Proper validation and error handling
# - Context-aware representation that removes write-only fields for read operations