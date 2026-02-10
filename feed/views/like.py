# feed/views/like_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from feed.models import Like, Post, Comment
from feed.serializers.like import LikeSerializer, LikeToggleSerializer
from feed.services import LikeService
from users.models import User


class LikeListView(APIView):
    """View for listing and creating likes"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get likes by the authenticated user"""
        content_type = request.query_params.get("content_type")
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))

        likes = LikeService.get_user_likes(
            user=request.user, content_type=content_type, limit=limit, offset=offset
        )

        serializer = LikeSerializer(likes, many=True, context={"request": request})

        return Response(
            {
                "count": len(likes),
                "next_offset": offset + len(likes),
                "results": serializer.data,
            }
        )

    def post(self, request):
        """Create a new like"""
        data = request.data.copy()
        data["user_id"] = request.user.id

        serializer = LikeSerializer(data=data, context={"request": request})

        if serializer.is_valid():
            like = serializer.save()
            return Response(
                LikeSerializer(like, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LikeToggleView(APIView):
    """View for toggling likes"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Toggle like on an object"""
        serializer = LikeToggleSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {
                    "liked": result["liked"],
                    "like_count": result["count"],
                    "message": "Liked" if result["liked"] else "Unliked",
                }
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LikeDetailView(APIView):
    """View for retrieving and deleting a specific like"""

    permission_classes = [IsAuthenticated]

    def get_object(self, like_id):
        """Get like object or return 404"""
        return get_object_or_404(Like, id=like_id)

    def get(self, request, like_id):
        """Retrieve a specific like"""
        like = self.get_object(like_id)

        # Users can only view their own likes
        if request.user != like.user:
            return Response(
                {"error": "You do not have permission to view this like"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = LikeSerializer(like, context={"request": request})
        return Response(serializer.data)

    def delete(self, request, like_id):
        """Delete a like"""
        like = self.get_object(like_id)

        # Check ownership
        if request.user != like.user:
            return Response(
                {"error": "You do not have permission to delete this like"},
                status=status.HTTP_403_FORBIDDEN,
            )

        success = LikeService.remove_like(
            user=request.user, content_type=like.content_type, object_id=like.object_id
        )

        if success:
            return Response({"message": "Like removed successfully"})

        return Response(
            {"error": "Failed to remove like"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ObjectLikesView(APIView):
    """View for getting likes on a specific object"""

    permission_classes = [AllowAny]

    def get(self, request, content_type, object_id):
        """Get likes for a specific object"""
        # Validate content type
        if content_type not in LikeService.CONTENT_TYPES:
            return Response(
                {
                    "error": f"Invalid content type. Must be one of {LikeService.CONTENT_TYPES}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if object exists and is accessible
        if content_type == "post":
            post = get_object_or_404(Post, id=object_id)
            if not post.is_public and request.user != post.user:
                return Response(
                    {"error": "You do not have permission to view likes for this post"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif content_type == "comment":
            comment = get_object_or_404(Comment, id=object_id)
            if not comment.post.is_public and request.user != comment.post.user:
                return Response(
                    {
                        "error": "You do not have permission to view likes for this comment"
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))

        likes = LikeService.get_likes_for_object(
            content_type=content_type, object_id=object_id, limit=limit, offset=offset
        )

        serializer = LikeSerializer(likes, many=True, context={"request": request})

        like_count = LikeService.get_like_count(content_type, object_id)

        return Response(
            {
                "content_type": content_type,
                "object_id": object_id,
                "total_likes": like_count,
                "count": len(likes),
                "next_offset": offset + len(likes),
                "results": serializer.data,
            }
        )


class LikeCheckView(APIView):
    """View for checking if user has liked an object"""

    permission_classes = [IsAuthenticated]

    def get(self, request, content_type, object_id):
        """Check if authenticated user has liked an object"""
        # Validate content type
        if content_type not in LikeService.CONTENT_TYPES:
            return Response(
                {
                    "error": f"Invalid content type. Must be one of {LikeService.CONTENT_TYPES}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        has_liked = LikeService.has_liked(
            user=request.user, content_type=content_type, object_id=object_id
        )

        like_count = LikeService.get_like_count(content_type, object_id)

        return Response(
            {
                "has_liked": has_liked,
                "like_count": like_count,
                "content_type": content_type,
                "object_id": object_id,
            }
        )


class RecentLikersView(APIView):
    """View for getting recent likers of an object"""

    permission_classes = [AllowAny]

    def get(self, request, content_type, object_id):
        """Get recent users who liked an object"""
        # Validate content type
        if content_type not in LikeService.CONTENT_TYPES:
            return Response(
                {
                    "error": f"Invalid content type. Must be one of {LikeService.CONTENT_TYPES}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check object accessibility
        if content_type == "post":
            post = get_object_or_404(Post, id=object_id)
            if not post.is_public and request.user != post.user:
                return Response(
                    {
                        "error": "You do not have permission to view likers for this post"
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        limit = int(request.query_params.get("limit", 10))

        recent_likers = LikeService.get_recent_likers(
            content_type=content_type, object_id=object_id, limit=limit
        )

        from users.serializers import UserSerializer

        serializer = UserSerializer(
            recent_likers, many=True, context={"request": request}
        )

        return Response(
            {
                "content_type": content_type,
                "object_id": object_id,
                "recent_likers": serializer.data,
            }
        )


class MostLikedContentView(APIView):
    """View for getting most liked content"""

    permission_classes = [AllowAny]

    def get(self, request, content_type):
        """Get most liked content of a specific type"""
        # Validate content type
        if content_type not in ["post", "comment"]:
            return Response(
                {"error": 'Content type must be either "post" or "comment"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        days = int(request.query_params.get("days", 7))
        limit = int(request.query_params.get("limit", 10))

        most_liked = LikeService.get_most_liked_content(
            content_type=content_type, days=days, limit=limit
        )

        # Custom response based on content type
        results = []
        for item in most_liked:
            result = {
                "type": item["type"],
                "object_id": item["object"].id,
                "like_count": item["like_count"],
            }

            if content_type == "post":
                from .post import PostFeedSerializer

                result["post"] = PostFeedSerializer(item["object"]).data
            elif content_type == "comment":
                from .comment import CommentSerializer

                result["comment"] = CommentSerializer(item["object"]).data

            results.append(result)

        return Response(
            {"content_type": content_type, "timeframe_days": days, "results": results}
        )


class UserLikeStatisticsView(APIView):
    """View for user like statistics"""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id=None):
        """Get like statistics for a user"""
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            # Users can only view their own statistics
            if request.user != target_user:
                return Response(
                    {"error": "You can only view your own like statistics"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            target_user = request.user

        statistics = LikeService.get_user_like_statistics(target_user)
        return Response(statistics)


class MutualLikesView(APIView):
    """View for getting mutual likes between two users"""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        """Get mutual likes between authenticated user and another user"""
        other_user = get_object_or_404(User, id=user_id)

        mutual_likes = LikeService.get_mutual_likes(
            user1=request.user, user2=other_user
        )

        return Response(
            {
                "user1_id": request.user.id,
                "user2_id": user_id,
                "mutual_likes": mutual_likes,
            }
        )
