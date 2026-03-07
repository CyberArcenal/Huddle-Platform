from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

from global_utils.pagination import UsersPagination

from ..services.user import UserService
from ..services.security_log import SecurityLogService
from ..services.login_session import LoginSessionService
from ..serializers.user import (
    UserCreateSerializer,
    UserUpdateSerializer,
    UserProfileSerializer,
    UserListSerializer,
    UserStatusSerializer
)
from ..models import User, UserStatus


class UserRegisterView(APIView):
    """View for user registration"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Register a new user"""
        serializer = UserCreateSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    user = serializer.save()
                    
                    # Log security event
                    SecurityLogService.create_log(
                        user=user,
                        event_type='signup',
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT'),
                        details='User registered successfully'
                    )
                    
                    # Return user data (excluding password)
                    response_serializer = UserProfileSerializer(
                        user, 
                        context={'request': request}
                    )
                    return Response(
                        {
                            'message': 'User registered successfully',
                            'user': response_serializer.data
                        },
                        status=status.HTTP_201_CREATED
                    )
                    
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class UserProfileView(APIView):
    """View for user profile operations"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get current user profile"""
        serializer = UserProfileSerializer(
            request.user,
            context={'request': request}
        )
        return Response(serializer.data)
    
    def put(self, request):
        """Update user profile"""
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                user = serializer.save()
                
                # Log activity
                from ..services.user_activity import UserActivityService
                UserActivityService.log_activity(
                    user=request.user,
                    action='update_profile',
                    description='User updated profile information',
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT')
                )
                
                return Response(
                    {
                        'message': 'Profile updated successfully',
                        'user': UserProfileSerializer(user, context={'request': request}).data
                    }
                )
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class UserDetailView(APIView):
    """View for retrieving specific user profiles"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, user_id):
        """Get user profile by ID"""
        try:
            user = UserService.get_user_by_id(user_id)
            
            if not user or user.status != UserStatus.ACTIVE:
                return Response(
                    {'error': 'User not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = UserProfileSerializer(
                user,
                context={'request': request}
            )
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserSearchView(APIView):
    """View for searching users"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Search users by query"""
        query = request.query_params.get('q', '').strip()
        if not query or len(query) < 2:
            return Response(
                {'error': 'Search query must be at least 2 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            users = UserService.search_users(query)   # returns full queryset
            paginator = UsersPagination()
            page = paginator.paginate_queryset(users, request)
            serializer = UserListSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserStatusUpdateView(APIView):
    """View for updating user status (admin/self)"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Update user status"""
        serializer = UserStatusSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Check if user can update their own status
                user_id = request.data.get('user_id', request.user.id)
                
                if user_id != request.user.id and not request.user.is_staff:
                    return Response(
                        {'error': 'Permission denied'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # Get user to update
                if user_id == request.user.id:
                    user = request.user
                else:
                    user = get_object_or_404(User, id=user_id)
                
                # Update status
                updated_user = serializer.update(user, serializer.validated_data)
                
                # Log security event
                SecurityLogService.create_log(
                    user=updated_user,
                    event_type='status_change',
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT'),
                    details=f'Status changed to {updated_user.status}'
                )
                
                return Response(
                    {
                        'message': f'User status updated to {updated_user.status}',
                        'user_id': updated_user.id,
                        'status': updated_user.status
                    }
                )
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class UserDeactivateView(APIView):
    """View for deactivating user account"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Deactivate user account"""
        try:
            # Verify password
            password = request.data.get('password')
            if not password or not request.user.check_password(password):
                return Response(
                    {'error': 'Invalid password'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Confirm deactivation
            confirm = request.data.get('confirm')
            if not confirm:
                return Response(
                    {'error': 'Please confirm deactivation'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Deactivate user
            user = UserService.deactivate_user(request.user)
            
            # Log security event
            SecurityLogService.create_log(
                user=user,
                event_type='account_deactivated',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                details='User deactivated account'
            )
            
            return Response(
                {
                    'message': 'Account deactivated successfully',
                    'user_id': user.id,
                    'status': user.status
                }
            )
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class VerifyUserView(APIView):
    """View for verifying user account"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Verify user account"""
        try:
            user = UserService.verify_user(request.user)
            
            # Log security event
            SecurityLogService.create_log(
                user=user,
                event_type='account_verified',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                details='User verified account'
            )
            
            return Response(
                {
                    'message': 'Account verified successfully',
                    'user_id': user.id,
                    'is_verified': user.is_verified
                }
            )
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class CheckUsernameView(APIView):
    """View for checking username availability"""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Check if username is available"""
        username = request.query_params.get('username', '').strip().lower()
        
        if not username:
            return Response(
                {'error': 'Username is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate username format
        if len(username) < 3:
            return Response({
                'available': False,
                'message': 'Username must be at least 3 characters'
            })
        
        if len(username) > 30:
            return Response({
                'available': False,
                'message': 'Username cannot exceed 30 characters'
            })
        
        if not username.replace('_', '').replace('.', '').isalnum():
            return Response({
                'available': False,
                'message': 'Username can only contain letters, numbers, underscores and dots'
            })
        
        # Check availability
        user = UserService.get_user_by_username(username)
        available = user is None
        
        return Response({
            'available': available,
            'username': username,
            'message': 'Username is available' if available else 'Username is taken'
        })


class CheckEmailView(APIView):
    """View for checking email availability"""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Check if email is available"""
        email = request.query_params.get('email', '').strip().lower()
        
        if not email:
            return Response(
                {'error': 'Email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate email format
        if '@' not in email or '.' not in email:
            return Response({
                'available': False,
                'message': 'Invalid email format'
            })
        
        # Check availability
        user = UserService.get_user_by_email(email)
        available = user is None
        
        return Response({
            'available': available,
            'email': email,
            'message': 'Email is available' if available else 'Email is already registered'
        })