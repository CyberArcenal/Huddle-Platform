from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from users.models.utilities import OTP_TYPES, OtpRequestTypes


class OtpRequest(models.Model):
    """One-time password request for email verification or login"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="otp_requests",
        null=True,
        blank=True,
    )
    otp_code = models.CharField(max_length=6)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(null=True, blank=True, max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempt_count = models.IntegerField(default=0)
    type = models.CharField(
        max_length=10, choices=OTP_TYPES, default=OtpRequestTypes.EMAIL
    )
    is_email_delivered = models.BooleanField(default=False)
    is_phone_delivered = models.BooleanField(default=False)

    def clean(self):
        if not self.type in dict(OTP_TYPES):
            raise ValidationError({"type": "Invalid OTP type."})

        if not self.email and not self.phone:
            raise ValueError("Either email or phone must be provided.")
        return super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "OTP Request"

    def __str__(self):
        return f"OTP for {self.user.username} - {self.otp_code}"
