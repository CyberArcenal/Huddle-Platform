# accounts/enums.py
from enum import Enum

class UserStatus(str, Enum):
    ACTIVE = "active"
    RESTRICTED = "restricted"
    SUSPENDED = "suspended"
    DELETED = "deleted"

class UserRole(str, Enum):
    VIEWER = "viewer"
    CUSTOMER = "customer"
    STAFF = "staff"
    MANAGER = "manager"
    ADMIN = "admin"