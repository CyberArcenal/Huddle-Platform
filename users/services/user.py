from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from typing import Optional, List, Dict, Any
from django.db import models

from ..models import User, UserStatus
from ..enums import UserStatus


class UserService:
    """Service for User model operations"""

    @staticmethod
    def create_user(
        username: str,
        email: str,
        password: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        is_active: bool = True,
        **extra_fields,
    ) -> User:
        """Create a new user with hashed password"""
        try:
            with transaction.atomic():
                user = User(
                    username=username,
                    email=email,
                    first_name=first_name or "",
                    last_name=last_name or "",
                    phone_number=phone_number or "",
                    is_active=is_active, 
                    **extra_fields,
                )
                user.set_password(password)
                user.full_clean()
                user.save()

                # Create default security settings
                from .user_security_settings import UserSecuritySettingsService
                UserSecuritySettingsService.create_default_settings(user)

                return user
        except IntegrityError as e:
            if "username" in str(e).lower():
                raise ValidationError(f"Username '{username}' already exists")
            elif "email" in str(e).lower():
                raise ValidationError(f"Email '{email}' already exists")
            raise
        except ValidationError as e:
            raise

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[User]:
        """Retrieve user by ID"""
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        """Retrieve user by email"""
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            return None

    @staticmethod
    def get_user_by_username(username: str) -> Optional[User]:
        """Retrieve user by username"""
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None

    @staticmethod
    def update_user(user: User, update_data: Dict[str, Any]) -> User:
        """Update user information"""
        try:
            with transaction.atomic():
                # Handle password separately
                if "password" in update_data:
                    user.set_password(update_data.pop("password"))

                # Update other fields
                for field, value in update_data.items():
                    if hasattr(user, field):
                        setattr(user, field, value)

                user.full_clean()
                user.save()
                return user
        except ValidationError as e:
            raise

    @staticmethod
    def update_status(user: User, status: UserStatus) -> User:
        """Update user account status"""
        user.status = status
        user.save()
        return user

    @staticmethod
    def deactivate_user(user: User) -> User:
        """Deactivate user account"""
        user.status = UserStatus.RESTRICTED
        user.is_active = False
        user.save()

        # Logout all sessions
        from .login_session import LoginSessionService

        LoginSessionService.deactivate_all_user_sessions(user)

        return user

    @staticmethod
    def delete_user(user: User, soft_delete: bool = True) -> bool:
        """Delete user account (soft or hard delete)"""
        try:
            with transaction.atomic():
                if soft_delete:
                    user.status = UserStatus.DELETED
                    user.is_active = False
                    user.save()

                    # Anonymize sensitive data
                    user.email = f"deleted_{user.id}@deleted.com"
                    user.username = f"deleted_{user.id}"
                    user.first_name = "Deleted"
                    user.last_name = "User"
                    user.phone_number = ""
                    user.profile_picture = None
                    user.cover_photo = None
                    user.bio = ""
                    user.save()

                    # Deactivate all sessions
                    from .login_session import LoginSessionService

                    LoginSessionService.deactivate_all_user_sessions(user)
                else:
                    user.delete()

                return True
        except Exception:
            return False

    @staticmethod
    def search_users(query: str, limit: int = 20) -> List[User]:
        """Search users by username, email, or name"""
        return User.objects.filter(status=UserStatus.ACTIVE).filter(
            models.Q(username__icontains=query)
            | models.Q(email__icontains=query)
            | models.Q(first_name__icontains=query)
            | models.Q(last_name__icontains=query)
        )[:limit]

    @staticmethod
    def verify_user(user: User) -> User:
        """Mark user as verified"""
        user.is_verified = True
        user.save()
        return user
