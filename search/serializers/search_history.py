# serializers.py
from rest_framework import serializers

from search.models.search_history import SearchHistory

class SearchHistorySerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    formatted_time = serializers.SerializerMethodField()
    
    class Meta:
        model = SearchHistory
        fields = [
            'id', 'user', 'username', 'query', 'search_type', 
            'results_count', 'searched_at', 'formatted_time'
        ]
        read_only_fields = ['id', 'user', 'searched_at']
    
    def get_formatted_time(self, obj) -> str:
        """Format date time for better readability"""
        from django.utils import timezone
        from django.utils.timesince import timesince
        
        now = timezone.now()
        if (now - obj.searched_at).days < 1:
            return f"{timesince(obj.searched_at)} ago"
        return obj.searched_at.strftime("%b %d, %Y %I:%M %p")
    
    def validate_query(self, value):
        """Validate and clean search query"""
        if not value or not value.strip():
            raise serializers.ValidationError("Search query cannot be empty")
        return value.strip()
    
    def validate_search_type(self, value):
        """Validate search type"""
        valid_types = ['all', 'users', 'groups', 'posts']
        if value not in valid_types:
            raise serializers.ValidationError(
                f"Search type must be one of: {', '.join(valid_types)}"
            )
        return value


class PopularSearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    search_type = serializers.CharField()
    count = serializers.IntegerField()
    last_searched = serializers.DateTimeField()
    
    class Meta:
        fields = ['query', 'search_type', 'count', 'last_searched']


class SearchSuggestionSerializer(serializers.Serializer):
    query = serializers.CharField()
    search_type = serializers.CharField(source='type')
    frequency = serializers.IntegerField(default=1)
    
    class Meta:
        fields = ['query', 'search_type', 'frequency']


class SearchStatisticsSerializer(serializers.Serializer):
    total_searches = serializers.IntegerField()
    results_statistics = serializers.DictField()
    type_breakdown = serializers.ListField()
    most_common_query = serializers.CharField(allow_null=True)
    most_common_query_count = serializers.IntegerField()
    recent_searches = serializers.ListField()
    period_days = serializers.IntegerField()
    user_specific = serializers.BooleanField()
    
    class Meta:
        fields = '__all__'


class ClearHistoryRequestSerializer(serializers.Serializer):
    older_than_days = serializers.IntegerField(
        min_value=1, 
        max_value=365, 
        required=False, 
        help_text="Clear history older than X days"
    )
    search_type = serializers.CharField(
        required=False, 
        help_text="Clear history of specific type"
    )
    
    def validate_search_type(self, value):
        valid_types = ['all', 'users', 'groups', 'posts']
        if value and value not in valid_types:
            raise serializers.ValidationError(
                f"Search type must be one of: {', '.join(valid_types)}"
            )
        return value

class RecordSearchInputSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=255, required=True, help_text="Search query")
    search_type = serializers.ChoiceField(
        choices=['all', 'users', 'groups', 'posts'],
        default='all',
        help_text="Type of search"
    )
    results_count = serializers.IntegerField(default=0, min_value=0, help_text="Number of results returned")