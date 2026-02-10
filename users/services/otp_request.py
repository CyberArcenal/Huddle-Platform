import random
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import Optional
from ..models import OtpRequest, User


class OtpRequestService:
    """Service for OtpRequest model operations"""
    
    @staticmethod
    def generate_otp_code(length: int = 6) -> str:
        """Generate OTP code"""
        return ''.join([str(random.randint(0, 9)) for _ in range(length)])
    
    @staticmethod
    def create_otp_request(
        user: Optional[User] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        expires_in_minutes: int = 10,
        otp_type: str = "email"
    ) -> OtpRequest:
        """Create a new OTP request"""
        if not user and not email and not phone:
            raise ValueError("Either user, email, or phone must be provided")
        
        if otp_type not in dict(OtpRequest.OTP_TYPES):
            raise ValidationError(f"Invalid OTP type: {otp_type}")
        
        otp_code = OtpRequestService.generate_otp_code()
        expires_at = timezone.now() + timezone.timedelta(minutes=expires_in_minutes)
        
        otp_request = OtpRequest.objects.create(
            user=user,
            email=email,
            phone=phone,
            otp_code=otp_code,
            expires_at=expires_at,
            type=otp_type
        )
        return otp_request
    
    @staticmethod
    def validate_otp(
        otp_code: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        user: Optional[User] = None
    ) -> Optional[OtpRequest]:
        """Validate OTP code"""
        queryset = OtpRequest.objects.filter(
            otp_code=otp_code,
            is_used=False,
            expires_at__gt=timezone.now()
        )
        
        if email:
            queryset = queryset.filter(email=email)
        elif phone:
            queryset = queryset.filter(phone=phone)
        elif user:
            queryset = queryset.filter(user=user)
        else:
            return None
        
        try:
            otp_request = queryset.latest('created_at')
            return otp_request
        except OtpRequest.DoesNotExist:
            return None
    
    @staticmethod
    def mark_otp_used(otp_request: OtpRequest) -> OtpRequest:
        """Mark OTP as used"""
        otp_request.is_used = True
        otp_request.save()
        return otp_request
    
    @staticmethod
    def increment_attempt(otp_request: OtpRequest) -> OtpRequest:
        """Increment attempt count for OTP"""
        otp_request.attempt_count += 1
        otp_request.save()
        return otp_request
    
    @staticmethod
    def get_recent_otp_attempts(
        email: Optional[str] = None,
        phone: Optional[str] = None,
        user: Optional[User] = None,
        minutes: int = 15
    ) -> int:
        """Count recent OTP attempts"""
        time_threshold = timezone.now() - timezone.timedelta(minutes=minutes)
        
        queryset = OtpRequest.objects.filter(
            created_at__gte=time_threshold
        )
        
        if email:
            queryset = queryset.filter(email=email)
        elif phone:
            queryset = queryset.filter(phone=phone)
        elif user:
            queryset = queryset.filter(user=user)
        
        return queryset.count()
    
    @staticmethod
    def cleanup_expired_otps() -> int:
        """Delete expired OTPs and return count"""
        expired_otps = OtpRequest.objects.filter(
            expires_at__lt=timezone.now()
        )
        count = expired_otps.count()
        expired_otps.delete()
        return count
    
    @staticmethod
    def mark_delivery_status(
        otp_request: OtpRequest,
        email_delivered: bool = False,
        phone_delivered: bool = False
    ) -> OtpRequest:
        """Update delivery status for OTP"""
        if email_delivered:
            otp_request.is_email_delivered = True
        if phone_delivered:
            otp_request.is_phone_delivered = True
        
        otp_request.save()
        return otp_request