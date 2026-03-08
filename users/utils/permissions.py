from rest_framework import permissions
from django.utils.translation import gettext_lazy as _
from global_utils.security import get_client_ip
from django.contrib.auth import get_user_model

from users.enums import UserRole
USER = get_user_model()



class BaseUserTypePermission(permissions.BasePermission):
    """Base class for user type permissions"""
    message = _("You do not have permission to perform this action.")
    ALLOWED_TYPES = []

    def has_permission(self, request, view):
        user = request.user
        allowed = bool(
            user.is_authenticated and getattr(user, "user_type", None) in self.ALLOWED_TYPES
        )
        if not allowed and user.is_authenticated:
            pass
        return allowed

class IsAdmin(BaseUserTypePermission):
    ALLOWED_TYPES = ["admin"]

class IsManager(BaseUserTypePermission):
    ALLOWED_TYPES = ["manager"]

class IsStaff(BaseUserTypePermission):
    ALLOWED_TYPES = ["staff"]

class IsCustomer(BaseUserTypePermission):
    ALLOWED_TYPES = ["customer"]

class IsViewer(BaseUserTypePermission):
    ALLOWED_TYPES = ["viewer"]

class IsAccountActive(permissions.BasePermission):
    """Allows access only to users whose status is active"""
    message = _("Your account is not active.")

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.is_authenticated and getattr(user, "status", None) == 'active'
        )
def is_admin(user) -> bool:
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN]

def is_staff(user) -> bool:
    """Helper function to check if user has edit permissions"""
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN, UserRole.STAFF, UserRole.MANAGER]

def can_edit(user) -> bool:
    """Helper function to check if user has edit permissions"""
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN, UserRole.STAFF, UserRole.MANAGER]

def can_approve(user) -> bool:
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN, UserRole.MANAGER]

def can_create(user) -> bool:
    """Helper function to check if user has edit permissions"""
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN, UserRole.STAFF, UserRole.MANAGER]

def can_read(user) -> bool:
    """Helper function to check if user has read permissions"""
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN, UserRole.STAFF, UserRole.MANAGER, UserRole.VIEWER]

def can_delete(user) -> bool:
    """Helper function to check if user has delete permissions"""
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN]

def can_confirm(user) -> bool:
    """Helper function to check if user can confirm purchases/orders"""
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN, UserRole.MANAGER]

def can_receive(user) -> bool:
    """Helper function to check if user can mark purchases/orders as received"""
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN, UserRole.STAFF]

def can_cancel(user) -> bool:
    """Helper function to check if user can cancel purchases/orders"""
    if not isinstance(user, USER):
        return False
    return user.user_type in [UserRole.ADMIN, UserRole.MANAGER]