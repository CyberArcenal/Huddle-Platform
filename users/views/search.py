
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db.models import Q

from ..serializers.search import (
    UserSearchSerializer,
    SearchResultSerializer,
    AdvancedSearchSerializer
)
from ..models import User, UserStatus


class UserSearchView(APIView):
    """View for searching users with basic search"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Search users with basic query"""
        serializer = UserSearchSerializer(data=request.query_params)
        
        if serializer.is_valid():
            try:
                users = serializer.search()
                
                result_serializer = SearchResultSerializer(
                    users,
                    many=True,
                    context={'request': request}
                )
                
                return Response({
                    'query': serializer.validated_data['query'],
                    'count': len(users),
                    'results': result_serializer.data
                })
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class AdvancedUserSearchView(APIView):
    """View for advanced user search with filters"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Advanced user search with multiple filters"""
        serializer = AdvancedSearchSerializer(data=request.query_params)
        
        if serializer.is_valid():
            try:
                search_result = serializer.search()
                
                # Serialize results
                result_serializer = SearchResultSerializer(
                    search_result['results'],
                    many=True,
                    context={'request': request}
                )
                
                return Response({
                    'query': request.query_params,
                    'pagination': {
                        'total_count': search_result['total_count'],
                        'total_pages': search_result['total_pages'],
                        'current_page': search_result['current_page'],
                        'page_size': search_result['page_size'],
                        'has_next': search_result['has_next'],
                        'has_previous': search_result['has_previous']
                    },
                    'count': len(search_result['results']),
                    'results': result_serializer.data
                })
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class SearchAutocompleteView(APIView):
    """View for search autocomplete suggestions"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get autocomplete suggestions for user search"""
        query = request.query_params.get('q', '').strip()
        
        if not query or len(query) < 2:
            return Response({
                'query': query,
                'suggestions': []
            })
        
        try:
            # Search in username, first name, last name
            users = User.objects.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query),
                status=UserStatus.ACTIVE,
                is_active=True
            ).order_by('username')[:10]  # Limit to 10 suggestions
            
            suggestions = []
            for user in users:
                suggestion = {
                    'id': user.id,
                    'username': user.username,
                    'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
                    'type': 'user'
                }
                
                # Add profile picture if available
                if user.profile_picture:
                    suggestion['profile_picture_url'] = request.build_absolute_uri(
                        user.profile_picture.url
                    )
                
                suggestions.append(suggestion)
            
            return Response({
                'query': query,
                'suggestions': suggestions
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SearchByUsernameView(APIView):
    """View for searching users by exact or partial username"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Search users by username"""
        username = request.query_params.get('username', '').strip().lower()
        
        if not username:
            return Response(
                {'error': 'Username is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Try exact match first
            exact_match = User.objects.filter(
                username__iexact=username,
                status=UserStatus.ACTIVE
            ).first()
            
            if exact_match:
                from ..serializers.user import UserProfileSerializer
                serializer = UserProfileSerializer(
                    exact_match,
                    context={'request': request}
                )
                return Response({
                    'match_type': 'exact',
                    'results': [serializer.data]
                })
            
            # If no exact match, search for partial matches
            partial_matches = User.objects.filter(
                username__icontains=username,
                status=UserStatus.ACTIVE
            ).order_by('username')[:20]
            
            from ..serializers.user import UserListSerializer
            serializer = UserListSerializer(
                partial_matches,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'match_type': 'partial',
                'count': len(partial_matches),
                'results': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SearchByEmailView(APIView):
    """View for searching users by email (admin only)"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get(self, request):
        """Search users by email (admin only)"""
        email = request.query_params.get('email', '').strip().lower()
        
        if not email:
            return Response(
                {'error': 'Email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Only allow exact or partial email search for admins
            users = User.objects.filter(
                email__icontains=email
            ).order_by('email')[:50]  # Limit results for admin search
            
            from ..serializers.user import UserListSerializer
            serializer = UserListSerializer(
                users,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'query': email,
                'count': len(users),
                'results': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class GlobalSearchView(APIView):
    """View for global search across multiple models (placeholder)"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Global search across users, posts, groups, etc."""
        query = request.query_params.get('q', '').strip()
        
        if not query or len(query) < 2:
            return Response({
                'query': query,
                'results': {
                    'users': [],
                    'total': 0
                }
            })
        
        try:
            # For now, only search users
            # In a real implementation, you would search across multiple models
            
            users = User.objects.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(email__icontains=query),
                status=UserStatus.ACTIVE
            ).order_by('username')[:10]
            
            from ..serializers.user import UserListSerializer
            user_serializer = UserListSerializer(
                users,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'query': query,
                'results': {
                    'users': user_serializer.data,
                    'users_count': len(users),
                    'total': len(users)
                }
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )