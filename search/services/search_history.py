from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from typing import Optional, List, Dict, Any, Tuple
from ..models import SearchHistory, User
from django.db.models import Count, Avg, Max, Min


class SearchHistoryService:
    """Service for SearchHistory model operations"""
    
    SEARCH_TYPES = ['all', 'users', 'groups', 'posts']
    
    @staticmethod
    def record_search(
        user: Optional[User] = None,
        query: str = "",
        search_type: str = "all",
        results_count: int = 0,
        **extra_fields
    ) -> SearchHistory:
        """Record a search query in history"""
        if not query or not query.strip():
            raise ValidationError("Search query cannot be empty")
        
        # Validate search_type
        if search_type not in SearchHistoryService.SEARCH_TYPES:
            raise ValidationError(
                f"Search type must be one of {SearchHistoryService.SEARCH_TYPES}"
            )
        
        # Clean query
        clean_query = query.strip()
        
        try:
            with transaction.atomic():
                # Check if similar recent search exists (same query and type within last hour)
                one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
                recent_similar = SearchHistory.objects.filter(
                    user=user,
                    query=clean_query,
                    search_type=search_type,
                    searched_at__gte=one_hour_ago
                ).first()
                
                if recent_similar:
                    # Update existing record
                    recent_similar.results_count = results_count
                    recent_similar.searched_at = timezone.now()
                    recent_similar.save()
                    return recent_similar
                
                # Create new record
                search_history = SearchHistory.objects.create(
                    user=user,
                    query=clean_query,
                    search_type=search_type,
                    results_count=results_count,
                    **extra_fields
                )
                return search_history
        except IntegrityError as e:
            raise ValidationError(f"Failed to record search: {str(e)}")
    
    @staticmethod
    def get_user_search_history(
        user: User,
        limit: int = 50,
        offset: int = 0,
        search_type: Optional[str] = None,
        days: Optional[int] = None
    ) -> List[SearchHistory]:
        """Get search history for a user"""
        queryset = SearchHistory.objects.filter(user=user)
        
        if search_type:
            queryset = queryset.filter(search_type=search_type)
        
        if days:
            time_threshold = timezone.now() - timezone.timedelta(days=days)
            queryset = queryset.filter(searched_at__gte=time_threshold)
        
        return list(queryset.order_by('-searched_at')[offset:offset + limit])
    
    @staticmethod
    def get_anonymous_search_history(
        session_key: str = "",
        limit: int = 20,
        days: int = 7
    ) -> List[SearchHistory]:
        """Get search history for anonymous users (by session)"""
        if not session_key:
            return []
        
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        # Note: You might need to adjust this if you track anonymous users differently
        # This assumes anonymous searches have no user but might have a session_key in metadata
        # You may need to modify the model to include session_key or use a different approach
        return []
    
    @staticmethod
    def get_recent_searches(
        user: Optional[User] = None,
        limit: int = 10,
        unique_queries: bool = True
    ) -> List[str]:
        """Get recent search queries (just the query strings)"""
        if user:
            queryset = SearchHistory.objects.filter(user=user)
        else:
            # For now, return empty for anonymous
            # You might implement session-based tracking
            return []
        
        if unique_queries:
            # Get distinct queries, most recent first
            # Using PostgreSQL's distinct on, for other DBs you might need a different approach
            try:
                # This works well with PostgreSQL
                recent_searches = queryset.order_by('query', '-searched_at').distinct('query')
            except:
                # Fallback for other databases
                recent_searches = queryset.order_by('-searched_at')
                seen_queries = set()
                unique_results = []
                for search in recent_searches:
                    if search.query not in seen_queries:
                        unique_results.append(search)
                        seen_queries.add(search.query)
                recent_searches = unique_results
        else:
            recent_searches = queryset.order_by('-searched_at')
        
        return [search.query for search in recent_searches[:limit]]
    
    @staticmethod
    def get_popular_searches(
        days: int = 7,
        limit: int = 10,
        search_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get popular search queries within a time period"""
        from django.db.models import Count
        
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        queryset = SearchHistory.objects.filter(
            searched_at__gte=time_threshold
        )
        
        if search_type:
            queryset = queryset.filter(search_type=search_type)
        
        # Group by query and count occurrences
        popular = queryset.values('query', 'search_type').annotate(
            count=Count('id')
        ).order_by('-count', 'query')[:limit]
        
        # For each query, get the last searched time
        result = []
        for item in popular:
            last_search = SearchHistory.objects.filter(
                query=item['query'],
                search_type=item['search_type']
            ).order_by('-searched_at').first()
            
            result.append({
                'query': item['query'],
                'search_type': item['search_type'],
                'count': item['count'],
                'last_searched': last_search.searched_at if last_search else None
            })
        
        return result
    
    @staticmethod
    def get_user_popular_searches(
        user: User,
        days: int = 30,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get user's most frequent searches"""
        from django.db.models import Count
        
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        popular = SearchHistory.objects.filter(
            user=user,
            searched_at__gte=time_threshold
        ).values('query', 'search_type').annotate(
            count=Count('id'),
            last_searched=timezone.now()  # Placeholder, will update below
        ).order_by('-count', 'query')[:limit]
        
        result = []
        for item in popular:
            last_search = SearchHistory.objects.filter(
                user=user,
                query=item['query'],
                search_type=item['search_type']
            ).order_by('-searched_at').first()
            
            result.append({
                'query': item['query'],
                'search_type': item['search_type'],
                'count': item['count'],
                'last_searched': last_search.searched_at if last_search else None
            })
        
        return result
    
    @staticmethod
    def clear_user_history(
        user: User,
        older_than_days: Optional[int] = None,
        search_type: Optional[str] = None
    ) -> Dict[str, int]:
        """Clear search history for a user"""
        queryset = SearchHistory.objects.filter(user=user)
        
        if older_than_days:
            time_threshold = timezone.now() - timezone.timedelta(days=older_than_days)
            queryset = queryset.filter(searched_at__lt=time_threshold)
        
        if search_type:
            queryset = queryset.filter(search_type=search_type)
        
        count = queryset.count()
        queryset.delete()
        
        return {
            'deleted': count,
            'user_id': user.id,
            'older_than_days': older_than_days,
            'search_type': search_type
        }
    
    @staticmethod
    def delete_search_entry(entry_id: int, user: Optional[User] = None) -> bool:
        """Delete a specific search history entry"""
        try:
            queryset = SearchHistory.objects.filter(id=entry_id)
            if user:
                queryset = queryset.filter(user=user)
            
            deleted_count, _ = queryset.delete()
            return deleted_count > 0
        except Exception:
            return False
    
    @staticmethod
    def get_search_statistics(
        user: Optional[User] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get search statistics for a user or globally"""
        from django.db.models import Count, Avg, Max, Min
        
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        queryset = SearchHistory.objects.filter(searched_at__gte=time_threshold)
        
        if user:
            queryset = queryset.filter(user=user)
        
        total_searches = queryset.count()
        
        # Breakdown by search type
        type_breakdown = queryset.values('search_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Results statistics
        results_stats = queryset.aggregate(
            avg_results=Avg('results_count'),
            max_results=Max('results_count'),
            min_results=Min('results_count'),
            total_results=Count('results_count')
        )
        
        # Most common query
        most_common = queryset.values('query').annotate(
            count=Count('id')
        ).order_by('-count').first()
        
        # Recent activity
        recent_activity = queryset.order_by('-searched_at')[:5]
        
        return {
            'total_searches': total_searches,
            'results_statistics': results_stats,
            'type_breakdown': list(type_breakdown),
            'most_common_query': most_common['query'] if most_common else None,
            'most_common_query_count': most_common['count'] if most_common else 0,
            'recent_searches': [
                {
                    'query': search.query,
                    'type': search.search_type,
                    'results': search.results_count,
                    'time': search.searched_at
                }
                for search in recent_activity
            ],
            'period_days': days,
            'user_specific': user is not None
        }
    
    @staticmethod
    def get_search_trends(
        days: int = 7,
        interval: str = 'day'
    ) -> List[Dict[str, Any]]:
        """Get search trends over time"""
        from django.db.models import Count, DateField
        from django.db.models.functions import Trunc
        
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        if interval == 'day':
            trunc_func = Trunc('searched_at', 'day', output_field=DateField())
        elif interval == 'hour':
            trunc_func = Trunc('searched_at', 'hour', output_field=DateField())
        else:
            trunc_func = Trunc('searched_at', 'day', output_field=DateField())
        
        trends = SearchHistory.objects.filter(
            searched_at__gte=time_threshold
        ).annotate(
            period=trunc_func
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')
        
        return list(trends)
    
    @staticmethod
    def get_suggestions(
        user: Optional[User] = None,
        prefix: str = "",
        limit: int = 10,
        include_anonymous: bool = False
    ) -> List[str]:
        """Get search suggestions based on past queries"""
        if not prefix.strip():
            return []
        
        queryset = SearchHistory.objects.filter(query__istartswith=prefix.strip())
        
        if user:
            # Include user's searches and popular searches
            user_searches = queryset.filter(user=user)
            if include_anonymous:
                popular_searches = queryset.exclude(user=user).values('query').annotate(
                    count=Count('id')
                ).order_by('-count')[:limit // 2]
            else:
                popular_searches = []
            
            # Combine and deduplicate
            user_suggestions = set(user_searches.values_list('query', flat=True)[:limit])
            popular_suggestions = set([item['query'] for item in popular_searches])
            
            suggestions = list(user_suggestions.union(popular_suggestions))[:limit]
        else:
            # For anonymous users, show popular searches
            suggestions = queryset.values('query').annotate(
                count=Count('id')
            ).order_by('-count').values_list('query', flat=True)[:limit]
        
        return list(suggestions)
    
    @staticmethod
    def get_related_searches(
        query: str,
        user: Optional[User] = None,
        limit: int = 5
    ) -> List[str]:
        """Get searches that often occur together with the given query"""
        from django.db.models import Count
        
        # Find searches made around the same time as this query
        time_threshold = timezone.now() - timezone.timedelta(days=30)
        
        # Get timestamps when this query was searched
        query_times = SearchHistory.objects.filter(
            query=query,
            searched_at__gte=time_threshold
        ).values_list('searched_at', flat=True)
        
        if not query_times:
            return []
        
        # Find other searches within 5 minutes of those timestamps
        related_searches = set()
        
        for query_time in query_times:
            window_start = query_time - timezone.timedelta(minutes=5)
            window_end = query_time + timezone.timedelta(minutes=5)
            
            related = SearchHistory.objects.filter(
                searched_at__range=(window_start, window_end),
                query__iexact=query
            ).exclude(query=query)
            
            if user:
                related = related.filter(user=user)
            
            for search in related[:limit]:
                related_searches.add(search.query)
        
        return list(related_searches)[:limit]
    
    @staticmethod
    def cleanup_old_history(days: int = 365) -> int:
        """Delete search history older than specified days"""
        time_threshold = timezone.now() - timezone.timedelta(days=days)
        
        old_history = SearchHistory.objects.filter(searched_at__lt=time_threshold)
        count = old_history.count()
        old_history.delete()
        
        return count
    
    @staticmethod
    def export_user_search_history(
        user: User,
        format: str = 'json',
        include_metadata: bool = True
    ) -> Dict[str, Any]:
        """Export user's search history in specified format"""
        searches = SearchHistory.objects.filter(user=user).order_by('-searched_at')
        
        if format == 'json':
            data = {
                'user_id': user.id,
                'username': user.username,
                'exported_at': timezone.now().isoformat(),
                'total_searches': searches.count(),
                'searches': [
                    {
                        'query': search.query,
                        'type': search.search_type,
                        'results_count': search.results_count,
                        'searched_at': search.searched_at.isoformat(),
                    }
                    for search in searches
                ]
            }
            
            if include_metadata:
                data['metadata'] = {
                    'app_version': '1.0',
                    'export_format': 'json',
                    'include_anonymous': False
                }
            
            return data
        
        # You could add other formats like CSV, XML, etc.
        raise ValueError(f"Unsupported export format: {format}")