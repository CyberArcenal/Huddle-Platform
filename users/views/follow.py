
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404

from global_utils.pagination import UsersPagination

from ..services.user_follow import UserFollowService
from ..services.user_activity import UserActivityService
from ..serializers.follow import (
    FollowUserSerializer,
    UnfollowUserSerializer,
    FollowStatsSerializer,
    FollowerListSerializer,
    FollowingListSerializer
)
from ..models import User


class FollowUserView(APIView):
    """View for following a user"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Follow a user"""
        serializer = FollowUserSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                follow = serializer.save()
                
                # Log activity
                UserActivityService.log_activity(
                    user=request.user,
                    action='follow',
                    description=f"Started following user ID: {follow.following.id}",
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT'),
                    metadata={'following_id': follow.following.id}
                )
                
                return Response(
                    {
                        'message': f'Now following {follow.following.username}',
                        'follow': {
                            'id': follow.id,
                            'follower_id': request.user.id,
                            'following_id': follow.following.id,
                            'created_at': follow.created_at
                        }
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


class UnfollowUserView(APIView):
    """View for unfollowing a user"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Unfollow a user"""
        serializer = UnfollowUserSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                success = serializer.unfollow()
                
                if success:
                    return Response(
                        {'message': 'Unfollowed successfully'},
                        status=status.HTTP_200_OK
                    )
                else:
                    return Response(
                        {'error': 'Failed to unfollow'},
                        status=status.HTTP_400_BAD_REQUEST
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


class FollowStatusView(APIView):
    """View for checking follow status"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, user_id):
        """Check if current user is following another user"""
        try:
            target_user = get_object_or_404(User, id=user_id)
            
            is_following = UserFollowService.is_following(
                follower=request.user,
                following=target_user
            )
            
            return Response({
                'is_following': is_following,
                'user_id': user_id,
                'username': target_user.username
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class FollowStatsView(APIView):
    """View for getting follow statistics"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, user_id=None):
        """Get follow statistics for a user"""
        try:
            if user_id:
                user = get_object_or_404(User, id=user_id)
            else:
                user = request.user
            
            # Get statistics
            followers_count = UserFollowService.get_follower_count(user)
            following_count = UserFollowService.get_following_count(user)
            
            # For mutual follows (only for current user)
            if user == request.user:
                # This is a simplified version - you might want to calculate mutual follows differently
                mutual_followers_count = 0  # Placeholder
            else:
                mutual_followers_count = 0
            
            stats_data = {
                'followers_count': followers_count,
                'following_count': following_count,
                'mutual_followers_count': mutual_followers_count
            }
            
            serializer = FollowStatsSerializer(stats_data)
            
            return Response({
                'user_id': user.id,
                'username': user.username,
                'stats': serializer.data
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class FollowersListView(APIView):
    """View for listing followers"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, user_id=None):
        """Get list of followers for a user"""
        try:
            if user_id:
                user = get_object_or_404(User, id=user_id)
            else:
                user = request.user

            # Get full queryset
            followers = UserFollowService.get_followers(user)

            paginator = UsersPagination()
            page = paginator.paginate_queryset(followers, request)
            serializer = FollowerListSerializer(
                page, many=True, context={'request': request, 'following': user}
            )
            return paginator.get_paginated_response(serializer.data)

        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FollowingListView(APIView):
    """View for listing users being followed"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, user_id=None):
        """Get list of users followed by a user"""
        try:
            if user_id:
                user = get_object_or_404(User, id=user_id)
            else:
                user = request.user

            following = UserFollowService.get_following(user)

            paginator = UsersPagination()
            page = paginator.paginate_queryset(following, request)
            serializer = FollowingListSerializer(
                page, many=True, context={'request': request, 'follower': user}
            )
            return paginator.get_paginated_response(serializer.data)

        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MutualFollowsView(APIView):
    """View for getting mutual follows between users"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, user_id):
        """Get mutual followers between current user and another user"""
        try:
            other_user = get_object_or_404(User, id=user_id)
            
            mutual_follows = UserFollowService.get_mutual_follows(
                user1=request.user,
                user2=other_user
            )
            
            from ..serializers.user import UserListSerializer
            serializer = UserListSerializer(
                mutual_follows,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'user1_id': request.user.id,
                'user2_id': other_user.id,
                'count': len(mutual_follows),
                'mutual_follows': serializer.data
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SuggestedUsersView(APIView):
    """View for getting suggested users to follow"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get suggested users based on mutual follows"""
        try:
            suggested_users = UserFollowService.get_suggested_users(
                user=request.user,
                limit=10
            )
            
            from ..serializers.user import UserListSerializer
            serializer = UserListSerializer(
                suggested_users,
                many=True,
                context={'request': request}
            )
            
            return Response({
                'count': len(suggested_users),
                'suggested_users': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )