# feed/views/post_views.py

import logging

from rest_framework.views import APIView, PermissionDenied
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
    inline_serializer,
)
from django.db import transaction
from feed.models import Post
from feed.serializers.base import PostStatsSerializers, SearchSerializer, UserPostStatisticsSerializer
from feed.serializers.post import (
    PostCreateSerializer,
    PostDisplaySerializer,
    PostFeedSerializer,
    PostUpdateSerializer,
)
from feed.services import PostService
from global_utils.pagination import StandardResultsSetPagination
from groups.models.group import Group
from users.models import User

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers for consistent documentation
# ----------------------------------------------------------------------

class PostCreateResponseData(serializers.Serializer):
    id = serializers.IntegerField()
    processing = serializers.BooleanField()


class PostCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostCreateResponseData(allow_null=True)


class PostUpdateResponseData(serializers.Serializer):
    post = PostDisplaySerializer()


class PostUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostUpdateResponseData(allow_null=True)


class PostDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class PostStatusResponseData(serializers.Serializer):
    id = serializers.IntegerField()
    processing = serializers.BooleanField()
    ready = serializers.BooleanField()
    media_urls = serializers.ListField(child=serializers.URLField(), allow_null=True)


class PostStatusResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostStatusResponseData(allow_null=True)


class PostDetailResponseData(serializers.Serializer):
    post = PostDisplaySerializer()


class PostDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostDetailResponseData(allow_null=True)


class PostListResponseData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PostFeedSerializer(many=True)


class PostListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostListResponseData()


class PostStatisticsResponseData(serializers.Serializer):
    stats = PostStatsSerializers()


class PostStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostStatisticsResponseData()


class UserPostStatisticsResponseData(serializers.Serializer):
    stats = UserPostStatisticsSerializer()


class UserPostStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserPostStatisticsResponseData()


class PostSearchResponseData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PostFeedSerializer(many=True)


class PostSearchResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostSearchResponseData()


class TrendingPostsResponseData(serializers.Serializer):
    timeframe_hours = serializers.IntegerField()
    min_likes = serializers.IntegerField()
    results = serializers.ListField(
        child=serializers.DictField()
    )


class TrendingPostsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = TrendingPostsResponseData()


class PostRestoreResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostDisplaySerializer(allow_null=True)


class PostShareResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostDisplaySerializer(allow_null=True)
    
class PostDeletedListResponseData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PostFeedSerializer(many=True)


class PostDeletedListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostDeletedListResponseData()


class PostArchivedListResponseData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PostFeedSerializer(many=True)


class PostArchivedListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PostArchivedListResponseData()


# ----------------------------------------------------------------------
# Helper to wrap paginated data into a consistent dict
# ----------------------------------------------------------------------
def wrap_paginated_data(paginator, page, request, serializer_class):
    """
    Construct a paginated data dict that matches PostListResponseData.
    """
    serializer = serializer_class(page, many=True, context={'request': request})
    data = {
        'page': paginator.page.number,
        'hasNext': paginator.page.has_next(),
        'hasPrev': paginator.page.has_previous(),
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class PostStatusView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Post's"],
        responses={200: PostStatusResponseSerializer},
        description="Check processing status of a post."
    )
    def get(self, request, post_id):
        post = get_object_or_404(Post, id=post_id)
        if post.privacy != 'public' and request.user != post.user:
            return Response(
                {
                    "status": False,
                    "message": "Forbidden",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN
            )

        media_urls = [
            request.build_absolute_uri(m.file.url)
            for m in post.media.all()
        ] if not post.processing else None

        data = {
            'id': post.id,
            'processing': post.processing,
            'ready': not post.processing and post.media.exists(),
            'media_urls': media_urls,
        }
        return Response(
            {
                "status": True,
                "message": "Post status retrieved.",
                "data": data,
            }
        )


class PostListView(APIView):
    """View for listing and creating posts"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["Post's"],
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="Filter by user ID",
                required=False,
            ),
            OpenApiParameter(
                name="feed",
                type=bool,
                description="Get personalized feed (requires auth)",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PostListResponseSerializer},
        description="List posts: public posts, posts by a specific user, or personalized feed for authenticated user.",
    )
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        user_posts = request.query_params.get("user_id")
        feed = request.query_params.get("feed", "false").lower() == "true"

        try:
            if user_posts:
                target_user = get_object_or_404(User, id=user_posts)
                include_processing = (request.user.is_authenticated and request.user == target_user)
                posts = PostService.get_user_posts(
                    user=target_user,
                    requester=request.user if request.user.is_authenticated else None,
                    include_processing=include_processing,
                )
            elif feed and user:
                posts = PostService.get_feed_posts(user=user, include_processing=False)
            else:
                posts = PostService.get_public_posts(exclude_user=user, include_processing=False)

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(posts, request)
            data = wrap_paginated_data(paginator, page, request, PostFeedSerializer)

            return Response(
                {
                    "status": True,
                    "message": "Posts retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.debug(e)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Post's"],
        request={
            'multipart/form-data': PostCreateSerializer,
        },
        responses={
            202: PostCreateResponseSerializer,
            400: PostCreateResponseSerializer,
        },
        description="Create a new post.",
    )
    @transaction.atomic
    def post(self, request):
        """Create a new post"""
        logger.debug(request.data)
        serializer = PostCreateSerializer(data=request.data, context={"request": request})

        if serializer.is_valid(raise_exception=True):
            post = serializer.save()
            response = {
                "status": True,
                "message": "Post upload accepted, processing in background.",
                "data": {
                    "id": post.id,
                    "processing": True,
                }
            }
            return Response(response, status=status.HTTP_202_ACCEPTED)

        logger.debug("Post create validation errors: %s", serializer.errors)
        response = {
            "status": False,
            "message": "Failed to create post.",
            "data": None,
        }
        return Response(response, status=status.HTTP_400_BAD_REQUEST)
    
    


class PostDetailView(APIView):
    """View for retrieving, updating, and deleting a specific post"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_object(self, post_id):
        post = PostService.get_post_by_id(post_id)
        if not post:
            return None
        return post

    @extend_schema(
        tags=["Post's"],
        responses={200: PostDetailResponseSerializer},
        description="Retrieve a single post by ID.",
    )
    def get(self, request, post_id):
        post = self.get_object(post_id)
        if not post:
            return Response(
                {
                    "status": False,
                    "message": "Post not found or deleted",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if not post.privacy == 'public' and request.user != post.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view this post",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        data = PostDisplaySerializer(post, context={"request": request}).data
        return Response(
            {
                "status": True,
                "message": "Post retrieved.",
                "data": {"post": data},
            }
        )

    @extend_schema(
        tags=["Post's"],
        request=PostUpdateSerializer,
        responses={200: PostUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update post", value={"content": "Updated content"}, request_only=True
            )
        ],
        description="Update a post (full or partial).",
    )
    @transaction.atomic
    def put(self, request, post_id):
        post = self.get_object(post_id)
        if not post:
            return Response(
                {
                    "status": False,
                    "message": "Post not found or deleted",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if request.user != post.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to update this post",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PostUpdateSerializer(
            post, data=request.data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            # Ensure user_id doesn't change
            if "user_id" in request.data and request.data["user_id"] != post.user.id:
                return Response(
                    {
                        "status": False,
                        "message": "Cannot change post owner",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            updated_post = serializer.save()
            data = PostDisplaySerializer(updated_post, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Post updated successfully.",
                    "data": {"post": data},
                }
            )

        return Response(
            {
                "status": False,
                "message": "Validation error.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        tags=["Post's"],
        request=PostUpdateSerializer,
        responses={200: PostUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update post", value={"content": "Updated content"}, request_only=True
            )
        ],
        description="Update a post (full or partial).",
    )
    @transaction.atomic
    def patch(self, request, post_id):
        logger.debug(request.data)
        post = self.get_object(post_id)
        if not post:
            return Response(
                {
                    "status": False,
                    "message": "Post not found or deleted",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if request.user != post.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to update this post",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PostUpdateSerializer(post, data=request.data, context={"request": request}, partial=True)

        if serializer.is_valid(raise_exception=True):
            post = serializer.save()
            response = {
                "status": True,
                "message": "Post upload accepted, processing in background.",
                "data": PostDisplaySerializer(post, context={"request": request}).data
            }
            return Response(response, status=status.HTTP_202_ACCEPTED)

        logger.debug("Post update validation errors: %s", serializer.errors)
        response = {
            "status": False,
            "message": "Failed to update post.",
            "data": None,
        }
        return Response(response, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["Post's"],
        parameters=[
            OpenApiParameter(
                name="hard",
                type=bool,
                description="Permanently delete instead of soft delete",
                required=False,
            ),
        ],
        responses={200: PostDeleteResponseSerializer},
        description="Delete a post (soft delete by default).",
    )
    @transaction.atomic
    def delete(self, request, post_id):
        post = self.get_object(post_id)
        if not post:
            return Response(
                {
                    "status": False,
                    "message": "Post not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if request.user != post.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to delete this post",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        hard_delete = request.query_params.get("hard", "false").lower() == "true"
        success = PostService.delete_post(post, soft_delete=not hard_delete)

        if success:
            message = "Post deleted successfully"
            if hard_delete:
                message = "Post permanently deleted"
            return Response(
                {
                    "status": True,
                    "message": message,
                    "data": None,
                }
            )

        return Response(
            {
                "status": False,
                "message": "Failed to delete post",
                "data": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class PostStatisticsView(APIView):
    """View for post statistics"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Post's"],
        responses={200: PostStatisticsResponseSerializer},
        description="Get statistics for a post (like count, comment count).",
    )
    def get(self, request, post_id):
        post = get_object_or_404(Post, id=post_id, is_deleted=False)

        if not post.privacy == 'public' and request.user != post.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to view statistics for this post",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        statistics = PostService.get_post_statistics(post)
        return Response(
            {
                "status": True,
                "message": "Statistics retrieved.",
                "data": {"stats": statistics},
            }
        )


class UserPostStatisticsView(APIView):
    """View for user's post statistics"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Post's"],
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (defaults to current user)",
                required=False,
            ),
        ],
        responses={200: UserPostStatisticsResponseSerializer},
        description="Get post statistics for a user (total posts, type breakdown, etc.).",
    )
    def get(self, request, user_id=None):
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
        else:
            target_user = request.user

        statistics = PostService.get_user_post_statistics(target_user)
        return Response(
            {
                "status": True,
                "message": "User statistics retrieved.",
                "data": {"stats": statistics},
            }
        )


class PostSearchView(APIView):
    """View for searching posts"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["Post's"],
        parameters=[
            OpenApiParameter(
                name="query", type=str, description="Search term", required=True
            ),
            OpenApiParameter(
                name="post_type",
                type=str,
                description="Filter by post type (text, image, video, poll)",
                required=False,
            ),
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
        responses={200: PostSearchResponseSerializer},
        description="Search posts by content.",
    )
    def get(self, request):
        serializer = SearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": "Invalid search parameters.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        user = request.user if request.user.is_authenticated else None
        posts = PostService.search_posts(
            query=data["query"], user=user, post_type=data.get("post_type")
        )

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(posts, request)
        paginated_data = wrap_paginated_data(paginator, page, request, PostFeedSerializer)

        return Response(
            {
                "status": True,
                "message": "Search results.",
                "data": paginated_data,
            }
        )


class TrendingPostsView(APIView):
    """View for trending posts"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Post's"],
        parameters=[
            OpenApiParameter(
                name="hours",
                type=int,
                description="Lookback period in hours",
                required=False,
            ),
            OpenApiParameter(
                name="min_likes",
                type=int,
                description="Minimum like count",
                required=False,
            ),
            OpenApiParameter(
                name="limit", type=int, description="Number of results", required=False
            ),
        ],
        responses={200: TrendingPostsResponseSerializer},
        description="Get trending posts (most liked within a time window).",
    )
    def get(self, request):
        hours = int(request.query_params.get("hours", 24))
        min_likes = int(request.query_params.get("min_likes", 5))
        limit = int(request.query_params.get("limit", 10))

        trending = PostService.get_trending_posts(
            hours=hours, min_likes=min_likes, limit=limit
        )

        # Build results list
        results = []
        for item in trending:
            results.append({
                "post": PostFeedSerializer(item["post"]).data,
                "like_count": item["like_count"],
                "comment_count": item["comment_count"],
            })

        data = {
            "timeframe_hours": hours,
            "min_likes": min_likes,
            "results": results,
        }
        return Response(
            {
                "status": True,
                "message": "Trending posts retrieved.",
                "data": data,
            }
        )


class PostRestoreView(APIView):
    """View for restoring deleted posts"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Post's"],
        responses={
            200: PostRestoreResponseSerializer,
            403: PostRestoreResponseSerializer,
            400: PostRestoreResponseSerializer,
        },
        description="Restore a soft-deleted post (only owner).",
    )
    @transaction.atomic
    def post(self, request, post_id):
        post = get_object_or_404(Post, id=post_id)

        if request.user != post.user:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to restore this post.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        success = PostService.restore_post(post)
        if success:
            return Response(
                {
                    "status": True,
                    "message": "Post restored successfully.",
                    "data": PostDisplaySerializer(post, context={"request": request}).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": False,
                "message": "Post is not deleted or could not be restored.",
                "data": None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class SharePostToGroupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Post's"],
        request=inline_serializer(
            name="ShareToGroupRequest",
            fields={
                "group_id": serializers.IntegerField(),
                "caption": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={
            201: PostShareResponseSerializer,
            400: PostShareResponseSerializer,
            403: PostShareResponseSerializer,
        },
        description="Share a post to a group, creating a new post in that group.",
    )
    @transaction.atomic
    def post(self, request, post_id):
        post = get_object_or_404(Post, id=post_id, is_deleted=False)
        group_id = request.data.get("group_id")
        caption = request.data.get("caption", "")

        if group_id is None:
            return Response(
                {
                    "status": False,
                    "message": "group_id is required.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        group = get_object_or_404(Group, id=group_id)

        try:
            new_post = PostService.share_post_to_group(
                user=request.user,
                original_post=post,
                group=group,
                caption=caption,
            )
            serializer = PostDisplaySerializer(new_post, context={"request": request})
            return Response(
                {
                    "status": True,
                    "message": "Post shared to group successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )
        except ValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Failed to share post to group.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PermissionDenied:
            return Response(
                {
                    "status": False,
                    "message": "You do not have permission to share to this group.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception as e:
            logger.exception("Unexpected error while sharing post %s to group %s: %s", post_id, group_id, e)
            return Response(
                {
                    "status": False,
                    "message": "An unexpected error occurred.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
            
# ----------------------------------------------------------------------
# Views for deleted and archived posts
# ----------------------------------------------------------------------

class PostDeletedListView(APIView):
    """
    Retrieve all soft-deleted posts belonging to the authenticated user.
    Only the owner can see their own deleted posts.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Post's"],
        parameters=[
            OpenApiParameter(name="page", type=int, description="Page number", required=False),
            OpenApiParameter(name="page_size", type=int, description="Results per page", required=False),
        ],
        responses={200: PostDeletedListResponseSerializer},
        description="Get a paginated list of soft-deleted posts for the authenticated user.",
    )
    def get(self, request):
        try:
            # Only posts where is_deleted=True and owned by the requesting user
            posts = Post.objects.filter(user=request.user, is_deleted=True).order_by('-created_at')

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(posts, request)
            data = wrap_paginated_data(paginator, page, request, PostFeedSerializer)

            return Response(
                {
                    "status": True,
                    "message": "Deleted posts retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving deleted posts for user %s", request.user.id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PostArchivedListView(APIView):
    """
    Retrieve all archived posts belonging to the authenticated user.
    Only the owner can see their own archived posts.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Post's"],
        parameters=[
            OpenApiParameter(name="page", type=int, description="Page number", required=False),
            OpenApiParameter(name="page_size", type=int, description="Results per page", required=False),
        ],
        responses={200: PostArchivedListResponseSerializer},
        description="Get a paginated list of archived posts for the authenticated user.",
    )
    def get(self, request):
        try:
            posts = Post.objects.filter(user=request.user, is_archived=True).order_by('-created_at')

            paginator = StandardResultsSetPagination()
            page = paginator.paginate_queryset(posts, request)
            data = wrap_paginated_data(paginator, page, request, PostFeedSerializer)

            return Response(
                {
                    "status": True,
                    "message": "Archived posts retrieved.",
                    "data": data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving archived posts for user %s", request.user.id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )