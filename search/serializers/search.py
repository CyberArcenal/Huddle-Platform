# serializers/search_serializer.py
import logging
from typing import Dict, Any, List

from rest_framework import serializers
from django.db.models import Q

from users.enums import UserStatus
from users.models.user import User

logger = logging.getLogger(__name__)


class UserSearchSerializer(serializers.Serializer):
    """Serializer for basic user search parameters"""

    query = serializers.CharField(
        required=True, min_length=1, max_length=100,
        help_text="Search term for username, email, or name"
    )
    only_active = serializers.BooleanField(
        required=False, default=True, help_text="Only show active users"
    )

    def search(self) -> List[User]:
        """Perform user search and return queryset (not paginated)"""
        query = self.validated_data["query"]
        only_active = self.validated_data.get("only_active", True)

        search_q = Q(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )
        if only_active:
            search_q &= Q(status=UserStatus.ACTIVE)

        return User.objects.filter(search_q)


class AdvancedSearchSerializer(serializers.Serializer):
    """Serializer for advanced user search filters"""

    username = serializers.CharField(required=False, max_length=50)
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False, max_length=50)
    last_name = serializers.CharField(required=False, max_length=50)
    is_verified = serializers.BooleanField(required=False)
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)
    order_by = serializers.ChoiceField(
        required=False, default="username",
        choices=[
            ("username", "Username"),
            ("-username", "Username (desc)"),
            ("created_at", "Join Date"),
            ("-created_at", "Join Date (desc)"),
            ("last_login", "Last Login"),
            ("-last_login", "Last Login (desc)"),
        ]
    )

    def build_filters(self) -> Dict[str, Any]:
        """Build dictionary of filters from validated data"""
        filters = {}
        if self.validated_data.get("username"):
            filters["username__icontains"] = self.validated_data["username"]
        if self.validated_data.get("email"):
            filters["email__icontains"] = self.validated_data["email"]
        if self.validated_data.get("first_name"):
            filters["first_name__icontains"] = self.validated_data["first_name"]
        if self.validated_data.get("last_name"):
            filters["last_name__icontains"] = self.validated_data["last_name"]
        if self.validated_data.get("is_verified") is not None:
            filters["is_verified"] = self.validated_data["is_verified"]
        if self.validated_data.get("created_after"):
            filters["created_at__gte"] = self.validated_data["created_after"]
        if self.validated_data.get("created_before"):
            filters["created_at__lte"] = self.validated_data["created_before"]
        return filters

    def get_queryset(self) -> List[User]:
        """Return the filtered and ordered queryset (without pagination)"""
        filters = self.build_filters()
        order_by = self.validated_data.get("order_by", "username")

        # Start with active users only
        queryset = User.objects.filter(status=UserStatus.ACTIVE)

        if filters:
            queryset = queryset.filter(**filters)

        queryset = queryset.order_by(order_by)
        return queryset