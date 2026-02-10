# serializers/search_serializer.py
from rest_framework import serializers
from django.db.models import Q
from typing import Dict, Any, List, Optional

from users.serializers.user import UserListSerializer

from ..models import User, UserFollow


class UserSearchSerializer(serializers.Serializer):
    """Serializer for user search parameters"""
    
    query = serializers.CharField(
        required=True,
        min_length=1,
        max_length=100,
        help_text="Search term for username, email, or name"
    )
    limit = serializers.IntegerField(
        required=False,
        default=20,
        min_value=1,
        max_value=100,
        help_text="Maximum number of results"
    )
    only_active = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Only show active users"
    )
    include_follow_status = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Include follow relationship status"
    )
    
    def search(self) -> List[User]:
        """Perform user search"""
        query = self.validated_data['query']
        limit = self.validated_data['limit']
        only_active = self.validated_data['only_active']
        
        # Build search query
        search_q = Q(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )
        
        if only_active:
            search_q &= Q(status='ACTIVE')
        
        # Execute search
        users = User.objects.filter(search_q)[:limit]
        
        return users


class SearchResultSerializer(UserListSerializer):
    """Enhanced serializer for search results"""
    
    is_following = serializers.SerializerMethodField()
    is_followed_by = serializers.SerializerMethodField()
    mutual_follows = serializers.SerializerMethodField()
    relevance_score = serializers.FloatField(default=0.0)
    
    class Meta(UserListSerializer.Meta):
        fields = UserListSerializer.Meta.fields + [
            'is_following', 'is_followed_by',
            'mutual_follows', 'relevance_score'
        ]
    
    def get_is_following(self, obj) -> bool:
        """Check if current user is following this user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return UserFollow.objects.filter(
                follower=request.user,
                following=obj
            ).exists()
        return False
    
    def get_is_followed_by(self, obj) -> bool:
        """Check if this user is following current user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return UserFollow.objects.filter(
                follower=obj,
                following=request.user
            ).exists()
        return False
    
    def get_mutual_follows(self, obj) -> int:
        """Get number of mutual followers"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Get users followed by both
            user_following = set(
                UserFollow.objects.filter(follower=request.user)
                .values_list('following_id', flat=True)
            )
            obj_following = set(
                UserFollow.objects.filter(follower=obj)
                .values_list('following_id', flat=True)
            )
            
            mutual = user_following.intersection(obj_following)
            return len(mutual)
        return 0


class AdvancedSearchSerializer(serializers.Serializer):
    """Serializer for advanced user search"""
    
    username = serializers.CharField(required=False, max_length=50)
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False, max_length=50)
    last_name = serializers.CharField(required=False, max_length=50)
    is_verified = serializers.BooleanField(required=False)
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)
    order_by = serializers.ChoiceField(
        required=False,
        default='username',
        choices=[
            ('username', 'Username'),
            ('-username', 'Username (desc)'),
            ('created_at', 'Join Date'),
            ('-created_at', 'Join Date (desc)'),
            ('last_login', 'Last Login'),
            ('-last_login', 'Last Login (desc)')
        ]
    )
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)
    
    def build_filters(self) -> Dict[str, Any]:
        """Build database filters from search parameters"""
        filters = {}
        
        if self.validated_data.get('username'):
            filters['username__icontains'] = self.validated_data['username']
        
        if self.validated_data.get('email'):
            filters['email__icontains'] = self.validated_data['email']
        
        if self.validated_data.get('first_name'):
            filters['first_name__icontains'] = self.validated_data['first_name']
        
        if self.validated_data.get('last_name'):
            filters['last_name__icontains'] = self.validated_data['last_name']
        
        if self.validated_data.get('is_verified') is not None:
            filters['is_verified'] = self.validated_data['is_verified']
        
        if self.validated_data.get('created_after'):
            filters['created_at__gte'] = self.validated_data['created_after']
        
        if self.validated_data.get('created_before'):
            filters['created_at__lte'] = self.validated_data['created_before']
        
        return filters
    
    def search(self) -> Dict[str, Any]:
        """Perform advanced search with pagination"""
        from django.core.paginator import Paginator
        
        filters = self.build_filters()
        order_by = self.validated_data.get('order_by', 'username')
        page = self.validated_data.get('page', 1)
        page_size = self.validated_data.get('page_size', 20)
        
        # Base queryset (only active users)
        queryset = User.objects.filter(status='ACTIVE')
        
        # Apply filters
        if filters:
            queryset = queryset.filter(**filters)
        
        # Order results
        queryset = queryset.order_by(order_by)
        
        # Paginate results
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        return {
            'results': page_obj.object_list,
            'total_count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page,
            'page_size': page_size,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous()
        }