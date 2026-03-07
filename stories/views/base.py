from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied

from global_utils.pagination import StoriesPagination
from stories.serializers.base import (
    StoryCleanupResponseSerializer, StoryCreateSerializer, StoryFeedSerializer,
    StoryHighlightSerializer, StoryRecentViewerSerializer, StoryRecommendationSerializer,
    StorySerializer, StoryStatsSerializer, StoryUpdateSerializer,
    StoryViewCountSerializer, StoryViewCreateSerializer, StoryViewSerializer
)
from stories.services.story import StoryService
from stories.services.story_feed import StoryFeedService
from stories.services.story_view import StoryViewService


class StoryListView(APIView):
    """Get active stories or create new story"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get active stories"""
        # Get full queryset from service (no limit/offset)
        stories = StoryService.get_active_stories(user=request.user)
        paginator = StoriesPagination()
        page = paginator.paginate_queryset(stories, request)
        serializer = StorySerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Create new story"""
        serializer = StoryCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            story = serializer.save()
            return Response(
                StorySerializer(story, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StoryDetailView(APIView):
    """Get, update, or delete a specific story"""
    permission_classes = [IsAuthenticated]

    def get_object(self, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return None
        return story

    def get(self, request, story_id):
        story = self.get_object(story_id)
        if not story:
            return Response(
                {'error': 'Story not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = StorySerializer(story, context={'request': request})
        return Response(serializer.data)

    def put(self, request, story_id):
        story = self.get_object(story_id)
        if not story:
            return Response(
                {'error': 'Story not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        if story.user != request.user:
            return Response(
                {'error': 'You can only update your own stories'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = StoryUpdateSerializer(data=request.data)
        if serializer.is_valid():
            updated_story = serializer.update(story, serializer.validated_data)
            return Response(
                StorySerializer(updated_story, context={'request': request}).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, story_id):
        story = self.get_object(story_id)
        if not story:
            return Response(
                {'error': 'Story not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        if story.user != request.user:
            return Response(
                {'error': 'You can only delete your own stories'},
                status=status.HTTP_403_FORBIDDEN
            )
        if StoryService.delete_story(story):
            return Response({'status': 'Story deleted'})
        return Response(
            {'error': 'Failed to delete story'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class StoryFeedView(APIView):
    """Get personalized story feed (structured, not paginated)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        include_own = request.query_params.get('include_own', 'true').lower() == 'true'
        limit_per_user = int(request.query_params.get('limit_per_user', 3))
        max_users = int(request.query_params.get('max_users', 20))

        feed = StoryFeedService.generate_story_feed(
            user=request.user,
            include_own_stories=include_own,
            limit_per_user=limit_per_user,
            max_users=max_users
        )

        serializer = StoryFeedSerializer(feed, many=True)
        return Response(serializer.data)


class StoryStatsView(APIView):
    """Get story statistics"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stats = StoryService.get_story_stats(request.user)
        serializer = StoryStatsSerializer(stats)
        return Response(serializer.data)


class StoryViewCreateView(APIView):
    """Record a story view"""
    permission_classes = [IsAuthenticated]

    def post(self, request, story_id):
        serializer = StoryViewCreateSerializer(
            data={'story_id': story_id},
            context={'request': request}
        )
        if serializer.is_valid():
            story_view = serializer.save()
            return Response(
                StoryViewSerializer(story_view).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StoryViewsListView(APIView):
    """Get views for a specific story"""
    permission_classes = [IsAuthenticated]

    def get(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {'error': 'Story not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        # Get full queryset (no limit/offset)
        views = StoryViewService.get_story_views(story)
        paginator = StoriesPagination()
        page = paginator.paginate_queryset(views, request)
        serializer = StoryViewSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class StoryViewCountView(APIView):
    """Get view count for a story"""
    permission_classes = [IsAuthenticated]

    def get(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {'error': 'Story not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        data = {
            'story_id': story.id,
            'view_count': StoryViewService.get_story_view_count(story),
            'unique_viewers': StoryViewService.get_unique_viewers_count(story)
        }
        serializer = StoryViewCountSerializer(data)
        return Response(serializer.data)


class StoryRecentViewersView(APIView):
    """Get recent viewers for a story (limited list, not paginated)"""
    permission_classes = [IsAuthenticated]

    def get(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {'error': 'Story not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        hours = int(request.query_params.get('hours', 24))
        limit = int(request.query_params.get('limit', 50))

        viewers = StoryViewService.get_recent_viewers(story, hours=hours, limit=limit)
        serializer = StoryRecentViewerSerializer(viewers, many=True)
        return Response(serializer.data)


class StoryDeactivateView(APIView):
    """Deactivate a story (soft delete)"""
    permission_classes = [IsAuthenticated]

    def post(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {'error': 'Story not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        if story.user != request.user:
            return Response(
                {'error': 'You can only deactivate your own stories'},
                status=status.HTTP_403_FORBIDDEN
            )
        StoryService.deactivate_story(story)
        return Response({'status': 'Story deactivated'})


class StoryExtendView(APIView):
    """Extend story expiration"""
    permission_classes = [IsAuthenticated]

    def post(self, request, story_id):
        story = StoryService.get_story_by_id(story_id)
        if not story:
            return Response(
                {'error': 'Story not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        if story.user != request.user:
            return Response(
                {'error': 'You can only extend your own stories'},
                status=status.HTTP_403_FORBIDDEN
            )
        additional_hours = int(request.data.get('additional_hours', 24))
        StoryService.extend_story_life(story, additional_hours=additional_hours)
        return Response({'status': f'Story extended by {additional_hours} hours'})


class UserStoriesView(APIView):
    """Get stories for a specific user"""
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id=None):
        target_user_id = user_id or request.user.id
        from users.models import User
        from django.shortcuts import get_object_or_404

        user = get_object_or_404(User, id=target_user_id)

        include_expired = request.query_params.get('include_expired', 'false').lower() == 'true'

        # Get full queryset (no limit/offset)
        stories = StoryService.get_user_stories(
            user=user,
            include_expired=include_expired
        )
        paginator = StoriesPagination()
        page = paginator.paginate_queryset(stories, request)
        serializer = StorySerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class FollowingStoriesView(APIView):
    """Get stories from followed users (structured feed, not paginated)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get('limit', 50))

        stories = StoryService.get_following_stories(user=request.user, limit=limit)
        serializer = StoryFeedSerializer(stories, many=True)
        return Response(serializer.data)


class StoryHighlightsView(APIView):
    """Get story highlights (limited list, not paginated)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get('days', 7))
        limit = int(request.query_params.get('limit', 10))

        highlights = StoryFeedService.get_story_highlights(
            user=request.user,
            days=days,
            limit=limit
        )
        serializer = StoryHighlightSerializer(highlights, many=True)
        return Response(serializer.data)


class StoryRecommendationsView(APIView):
    """Get story recommendations (limited list, not paginated)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get('limit', 5))

        recommendations = StoryFeedService.get_story_recommendations(
            user=request.user,
            limit=limit
        )
        serializer = StoryRecommendationSerializer(recommendations, many=True)
        return Response(serializer.data)


class StoryCleanupView(APIView):
    """Cleanup expired stories (admin only)"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can perform cleanup'},
                status=status.HTTP_403_FORBIDDEN
            )
        deactivate_only = request.data.get('deactivate_only', True)
        stats = StoryService.cleanup_expired_stories(deactivate_only=deactivate_only)
        serializer = StoryCleanupResponseSerializer(stats)
        return Response(serializer.data)


class StoriesByTypeView(APIView):
    """Get stories by type"""
    permission_classes = [IsAuthenticated]

    def get(self, request, story_type):
        active_only = request.query_params.get('active_only', 'true').lower() == 'true'

        # Get full queryset (no limit/offset)
        stories = StoryService.get_stories_by_type(
            story_type=story_type,
            active_only=active_only
        )
        paginator = StoriesPagination()
        page = paginator.paginate_queryset(stories, request)
        serializer = StorySerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class StoryViewStatsView(APIView):
    """Get viewing statistics for the current user"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stats = StoryViewService.get_user_story_view_stats(request.user)
        return Response(stats)


class MutualStoryViewsView(APIView):
    """Get mutual story viewing statistics between two users"""
    permission_classes = [IsAuthenticated]

    def get(self, request, other_user_id):
        from users.models import User
        from django.shortcuts import get_object_or_404

        other_user = get_object_or_404(User, id=other_user_id)

        stats = StoryViewService.get_mutual_story_views(request.user, other_user)
        return Response(stats)


class PopularStoriesView(APIView):
    """Get popular stories (limited list, not paginated)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        hours = int(request.query_params.get('hours', 24))
        limit = int(request.query_params.get('limit', 20))

        popular_stories = StoryViewService.get_popular_stories(hours=hours, limit=limit)
        return Response(popular_stories)