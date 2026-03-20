from django.conf import settings
from django.utils import timezone
from django.db import models


class BlacklistedAccessToken(models.Model):
    jti = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "blacklisted_access_tokens"

    def __str__(self):
        return f"Blacklisted token {self.jti} for {self.user}"

    @classmethod
    def is_blacklisted(cls, jti):
        """Check if a token jti is blacklisted"""
        return cls.objects.filter(jti=jti).exists()

    @classmethod
    def blacklist_token(cls, jti, user, expires_at):
        """Add a token to blacklist"""
        return cls.objects.get_or_create(
            jti=jti, defaults={"user": user, "expires_at": expires_at}
        )

    @classmethod
    def cleanup_expired(cls):
        """Remove expired blacklisted tokens"""
        cls.objects.filter(expires_at__lt=timezone.now()).delete()