import uuid
from rest_framework import serializers
from django.utils import timezone
import logging
from django.contrib.auth import get_user_model

from users.models.base import LoginCheckpoint, OtpRequestStatus
from users.serializers.user import UserMinimalSerializer

User = get_user_model()


logger = logging.getLogger(__name__)

class LoginCheckpointSerializer(serializers.ModelSerializer):
    # Nested serializers for read operations
    user_data = UserMinimalSerializer(source='user', read_only=True)
    
    # Display fields for read operations
    status_display = serializers.SerializerMethodField(read_only=True)
    
    # Conditional fields for write operations
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), 
        write_only=True
    )
    
    class Meta:
        model = LoginCheckpoint
        fields = [
            "id",
            "user",
            "user_data",
            "token",
            "created_at",
            "expires_at",
            "is_used",
            "status_display"
        ]
        read_only_fields = [
            "id",
            "token",
            "created_at",
            "expires_at",
            "is_used"
        ]
        extra_kwargs = {
            'token': {'read_only': True},
        }
    
    def get_status_display(self, obj) -> str:
        if obj.is_used:
            return "Used"
        elif timezone.now() > obj.expires_at:
            return "Expired"
        else:
            return "Active"
    
    def create(self, validated_data):
        try:
            # Generate a unique token
            validated_data['token'] = uuid.uuid4().hex
            
            # Set expiration time (assuming 15 minutes from creation)
            validated_data['expires_at'] = timezone.now() + timezone.timedelta(minutes=15)
            
            checkpoint = LoginCheckpoint.objects.create(**validated_data)
            logger.info(f"Login checkpoint created for user: {checkpoint.user.username}")
            return checkpoint
        except Exception as e:
            logger.error(f"Login checkpoint creation failed: {str(e)}")
            raise serializers.ValidationError(
                {"non_field_errors": [f"Creation failed: {str(e)}"]}
            )
    
    def update(self, instance, validated_data):
        # Only allow updating is_used field
        if 'is_used' in validated_data:
            instance.is_used = validated_data['is_used']
        
        try:
            instance.save()
            logger.info(f"Login checkpoint {instance.id} updated")
            return instance
        except Exception as e:
            logger.error(f"Login checkpoint update failed! ID: {instance.id} | Error: {str(e)}")
            raise serializers.ValidationError(
                {"non_field_errors": [f"Update failed: {str(e)}"]}
            )
    
    def to_representation(self, instance):
        """Customize output for read operations"""
        representation = super().to_representation(instance)
        
        # For read operations, remove write-only fields
        request = self.context.get("request")
        if request and request.method in ["GET", "HEAD", "OPTIONS"]:
            representation.pop("user", None)
        
        return representation
    
""" 
Example Usage:
# /api/v1/accounts/login-checkpoints/
# /api/v1/accounts/login-checkpoints/<int:id>/
# /api/v1/accounts/login-checkpoints/<int:id>/<slug:option>/

Create Login Checkpoint (POST):

json
{
  "user": 1
}
Get Login Checkpoint (GET) Response:

json
{
  "id": 1,
  "user_data": {
    "id": 1,
    "full_name": "John Doe",
    "username": "johndoe",
    "email": "john@example.com",
    "first_name": "John",
    "last_name": "Doe"
  },
  "token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "created_at": "2023-01-01T12:00:00Z",
  "expires_at": "2023-01-01T12:15:00Z",
  "is_used": false,
  "status_display": "Active"
}
Update Login Checkpoint (PATCH):

json
{
  "is_used": true
}

"""