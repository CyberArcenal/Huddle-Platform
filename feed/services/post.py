import threading

from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Q, Count, QuerySet
from typing import Iterable, Optional, List, Dict, Any, Tuple
from django.contrib.contenttypes.models import ContentType
from admin_pannel.services.reported_content import ReportedContentService
from analytics.services.trend_score import TrendScoreService
from feed.models.post import POST_TYPES

from feed.serializers.comment import CommentDisplaySerializer
from feed.services.bookmark import BookmarkService
from feed.services.comment import CommentService
from feed.services.media import MediaProcessingService
from feed.services.reaction import ReactionService
from feed.services.share import ShareService
from feed.services.view import ViewService
from feed.tasks.media import process_media_task
from groups.models.group import Group
from groups.services.group import GroupService
from groups.services.group_member import GroupMemberService
from users.models import User
from users.services.user_follow import UserFollowService
from ..models import Post, Media
import uuid
MAX_FEED_LIMIT = getattr(settings, "MAX_FEED_LIMIT", 100)

class PostService:
    """Service for Post model operations"""

    @staticmethod
    def create_post(
        user: User,
        content: str,
        post_type: str = "text",
        media_files: Optional[List] = None,  # list of uploaded files
        privacy: str = "followers",
        group: Group = None,
        tag_users: Optional[List[User]] = None,
        **extra_fields,
    ) -> Post:
        """Create a new post with optional media files"""
        # Validate post type
        valid_types = [choice[0] for choice in POST_TYPES]
        if post_type not in valid_types:
            raise ValidationError(f"Post type must be one of {valid_types}")
        
        if group and not isinstance(group, Group):
            raise ValidationError(f"Group: {group} is not an instance")
        
        if not isinstance(user, User):
            raise ValidationError(f"User: {user} is not an intance")

        # Validate based on post type
        if post_type == "text" and not content.strip():
            raise ValidationError("Text posts require content")
        elif post_type in ["image", "video"] and not media_files:
            raise ValidationError(
                f"{post_type.capitalize()} posts require at least one media file."
            )

        try:
            with transaction.atomic():
                post = Post.objects.create(
                    user=user,
                    content=content,
                    post_type=post_type,
                    privacy=privacy,
                    group=group,
                    **extra_fields,
                )
                if media_files:
                    post_ct = ContentType.objects.get_for_model(post)
                    for order, file in enumerate(media_files):
                        media = Media.objects.create(
                            content_type=post_ct,
                            object_id=post.id,
                            file=file,
                            order=order
                        )
                        threading.Thread(target=MediaProcessingService.process_media, args=(media,)).start()
                        process_media_task.delay(media.id)
                # handle tagged users
                if tag_users:
                    post.tag_users.set(tag_users)
                return post
        except IntegrityError as e:
            raise ValidationError(f"Failed to create post: {str(e)}")

    @staticmethod
    def get_post_by_id(
        post_id: int, requesting_user: Optional[User] = None
    ) -> Optional[Post]:
        try:
            post = Post.objects.get(id=post_id, is_deleted=False)
        except Post.DoesNotExist:
            return None

        # Kung may group, i-verify kung pwedeng makita ng requesting_user
        if post.group:
            if not GroupService.is_user_allowed_to_view(requesting_user, post.group):
                return None
            # O kaya i-check ang privacy ng post sa loob ng group
            # (depende sa implementation)
        else:
            # Personal post: i-check kung public o following
            if post.privacy == "public":
                return post
            if requesting_user and (
                post.user == requesting_user
                or UserFollowService.is_following(requesting_user, post.user)
            ):
                return post
            return None

        return post

    @staticmethod
    def get_user_posts(
        user: User, include_deleted: bool = False, limit: int = 50, offset: int = 0
    ) -> List[Post]:
        """Get posts by a specific user"""
        queryset = Post.objects.filter(user=user)

        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)

        return list(queryset.order_by("-created_at")[offset : offset + limit])

    @staticmethod
    def get_public_posts(
        exclude_user: Optional[User] = None, limit: int = 50, offset: int = 0
    ) -> List[Post]:
        """Get public posts from all users"""
        queryset = Post.objects.filter(privacy="public", is_deleted=False)

        if exclude_user:
            queryset = queryset.exclude(user=exclude_user)

        return list(queryset.order_by("-created_at")[offset : offset + limit])




   

    @staticmethod
    def _to_id_list(maybe_qs_or_list: Iterable) -> List[int]:
        """
        Convert a QuerySet, list of model instances, or list of ints to a list of ids.
        """
        if maybe_qs_or_list is None:
            return []
        # QuerySet: has values_list
        if hasattr(maybe_qs_or_list, "values_list"):
            return list(maybe_qs_or_list.values_list("id", flat=True))
        # List of model instances: try to extract .id attribute
        try:
            return [int(getattr(item, "id", item)) for item in maybe_qs_or_list]
        except Exception:
            # Fallback: empty list if unexpected shape
            return []

    @staticmethod
    def get_feed_posts(user: "User", limit: int = 50, offset: int = 0) -> List["Post"]:
        """
        Return a list of posts for the user's feed.

        - Handles service returns that may be QuerySet or list.
        - Uses ids for filtering to avoid embedding large querysets.
        """
        from groups.services import GroupMemberService
        from users.services import UserFollowService
        from feed.models.post import Post

        # sanitize limit/offset
        if limit <= 0:
            limit = 1
        limit = min(limit, MAX_FEED_LIMIT)
        if offset < 0:
            offset = 0

        # Get following users (could be QuerySet or list)
        following_qs = UserFollowService.get_following(user)
        following_ids = PostService._to_id_list(following_qs)

        # Get groups the user belongs to (could be QuerySet or list)
        user_groups_qs = GroupMemberService.get_user_groups(user)
        user_group_ids = PostService._to_id_list(user_groups_qs)

        # Build Q expressions with explicit grouping
        non_group_posts_q = (Q(user__in=following_ids) | Q(user=user)) & Q(group__isnull=True)
        group_posts_q = Q(group__in=user_group_ids) & Q(group__isnull=False)

        qs: QuerySet = (
            Post.objects.filter((non_group_posts_q | group_posts_q), is_deleted=False)
            .select_related("user", "group")
            .order_by("-created_at")
            .distinct()
        )

        feed_posts = qs[offset : offset + limit]
        return list(feed_posts)



    @staticmethod
    def update_post(post: Post, update_data: Dict[str, Any]) -> Post:
        """Update post information (excluding media)"""
        # Only allow update if post is not deleted
        if post.is_deleted:
            raise ValidationError("Cannot update a deleted post")

        try:
            with transaction.atomic():
                for field, value in update_data.items():
                    if hasattr(post, field) and field not in [
                        "id",
                        "user",
                        "created_at",
                    ]:
                        setattr(post, field, value)

                post.full_clean()
                post.save()
                return post
        except ValidationError as e:
            raise

    @staticmethod
    def delete_post(post: Post, soft_delete: bool = True) -> bool:
        """Delete a post (soft or hard delete)"""
        try:
            with transaction.atomic():
                if soft_delete:
                    post.is_deleted = True
                    post.save()
                else:
                    post.delete()
                return True
        except Exception:
            return False

    @staticmethod
    def restore_post(post: Post) -> bool:
        """Restore a soft-deleted post"""
        if not post.is_deleted:
            return False

        post.is_deleted = False
        post.save()
        return True

    @staticmethod
    def search_posts(
        query: str,
        user: Optional[User] = None,
        post_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Post]:
        """Search posts by content"""
        queryset = Post.objects.filter(content__icontains=query, is_deleted=False)

        if user:
            queryset = queryset.filter(user=user)

        if post_type:
            queryset = queryset.filter(post_type=post_type)

        return list(queryset.order_by("-created_at")[offset : offset + limit])
        
    def get_post_statistics(serializer, obj) -> Dict[str, Any]:
        request = serializer.context.get("request")
        user = request.user if request and request.user.is_authenticated else None
        is_author = False
        created_at = None
        updated_at = None
        try:
            created_at = obj.created_at
        except:pass
        try:
            updated_at = obj.updated_at
        except:pass
        try:
            is_author = user.id == obj.user.id if user else False
        except:pass

        return {
            "comment_count": CommentService.get_comment_count(obj),
            "like_count": ReactionService.get_like_count(obj, obj.id),
            "reaction_count": ReactionService.get_reaction_counts(obj, obj.id),
            "comments": CommentDisplaySerializer(
                CommentService.get_comments_for_object(obj, limit=10),
                many=True,
                context=serializer.context,
            ).data,
            "liked": ReactionService.has_liked(user=user, content_type=obj, object_id=obj.id) if user else False,
            "current_reaction": ReactionService.get_user_reaction(user, obj, obj.id) if user else None,
            "share_count": ShareService.get_share_count(obj),

 
            "view_count": ViewService.get_view_count(obj),
            "moots_who_reacted": ReactionService.get_friends_who_reacted_to_post(user, post_id=obj.id, content_type=obj, limit=10),
            "unique_viewers": ViewService.get_unique_viewers(obj),
            "bookmark_count": BookmarkService.get_bookmark_count(obj),
            "report_count": ReportedContentService.get_report_count(obj, object_id=obj.id),
            
            "trending_score": TrendScoreService.get_score(obj),
            "is_author": is_author,
            "created_at": created_at,
            "updated_at": updated_at,
        }


    @staticmethod
    def get_user_post_statistics(user: User) -> Dict[str, Any]:
        """Get post statistics for a user"""
        total_posts = Post.objects.filter(user=user, is_deleted=False).count()
        public_posts = Post.objects.filter(
            user=user, privacy="public", is_deleted=False
        ).count()
        private_posts = total_posts - public_posts

        # Post type breakdown
        type_breakdown = (
            Post.objects.filter(user=user, is_deleted=False)
            .values("post_type")
            .annotate(count=Count("id"))
        )

        return {
            "total_posts": total_posts,
            "public_posts": public_posts,
            "private_posts": private_posts,
            "type_breakdown": list(type_breakdown),
            "first_post_date": (
                Post.objects.filter(user=user).order_by("created_at").first().created_at
                if total_posts > 0
                else None
            ),
        }

    @staticmethod
    def get_trending_posts(
        hours: int = 24, min_likes: int = 5, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get trending posts (most liked within a time period)"""
        from .reaction import ReactionService

        time_threshold = timezone.now() - timezone.timedelta(hours=hours)

        # Get posts created within the time period
        recent_posts = Post.objects.filter(
            created_at__gte=time_threshold, is_deleted=False, privacy="public"
        )

        # Calculate like counts and filter
        trending = []
        for post in recent_posts:
            like_count = ReactionService.get_like_count("post", post.id)
            if like_count >= min_likes:
                trending.append(
                    {
                        "post": post,
                        "like_count": like_count,
                        "comment_count": post.comments.count(),
                    }
                )

        # Sort by like count (descending) and then by recency
        trending.sort(
            key=lambda x: (-x["like_count"], -x["post"].created_at.timestamp())
        )

        return trending[:limit]

    @staticmethod
    def cleanup_deleted_posts(days: int = 30) -> int:
        """Permanently delete posts that were soft-deleted more than X days ago"""
        time_threshold = timezone.now() - timezone.timedelta(days=days)

        old_deleted_posts = Post.objects.filter(
            is_deleted=True, updated_at__lt=time_threshold
        )
        count = old_deleted_posts.count()
        old_deleted_posts.delete()

        return count

    @staticmethod
    def share_post_to_group(
        user: User, original_post: Post, group, caption: str = ""
    ) -> Post:
        """Share an existing post to a group, creating a new post in that group."""
        # Check if user can post in group
        if not GroupMemberService.is_member(group, user):
            raise ValidationError(
                "You must be a member of the group to share posts here."
            )

        # Original post must not be deleted
        if original_post.is_deleted:
            raise ValidationError("Cannot share a deleted post.")

        try:
            with transaction.atomic():
                shared_post = Post.objects.create(
                    user=user,
                    group=group,
                    content=caption,  # optional caption from sharer
                    post_type="share",
                    privacy="public",  # group posts are visible per group rules
                    shared_post=original_post,
                )
                return shared_post
        except IntegrityError as e:
            raise ValidationError(f"Failed to share post: {str(e)}")
    
    @staticmethod
    def get_following_posts(user: User, limit: int = 20, offset: int = 0) -> List[Post]:
        """
        Get posts from users that the current user follows.
        """
        from users.services.user_follow import UserFollowService

        following_users = UserFollowService.get_following(user)
        if not following_users:
            return []

        # Get posts from followed users (personal posts only, not group posts)
        following_posts = Post.objects.filter(
            user__in=following_users,
            group__isnull=True,          # personal posts only
            is_deleted=False
        ).select_related('user').order_by('-created_at')

        return list(following_posts[offset:offset + limit])
    
    @staticmethod
    def get_friend_posts(user: User, limit: int = 20, offset: int = 0) -> List[Post]:
        """
        Get posts from users who are mutual followers (friends) of the current user.
        """
        from users.models import UserFollow
        from django.db.models import Q

        # Find users that follow the current user and are followed by the current user (mutual)
        # Equivalent to: friends = users who follow user and user follows them
        friends = User.objects.filter(
            Q(followers__follower=user) & Q(following__following=user)
        ).distinct()

        if not friends:
            return []

        friend_posts = Post.objects.filter(
            user__in=friends,
            group__isnull=True,          # personal posts only
            is_deleted=False
        ).select_related('user').order_by('-created_at')

        return list(friend_posts[offset:offset + limit])

    @staticmethod
    def get_user_posts(
        user_id: int, 
        requester: Optional[User] = None, 
        limit: int = 10, 
        offset: int = 0
    ) -> List[Post]:
        """
        Return posts of a specific user, filtered by privacy rules.
        """
        target_user = User.objects.get(id=user_id)
        queryset = Post.objects.filter(user=target_user, is_deleted=False)

        # Apply privacy filtering
        if requester and requester.is_authenticated:
            # If requester is the target user, they see all their own posts
            if requester == target_user:
                return list(queryset.order_by('-created_at')[offset:offset+limit])

            # Otherwise, apply privacy logic
            # Public posts: always visible
            public_posts = queryset.filter(privacy='public')
            # Followers-only posts: visible if requester follows target_user
            followers_posts = queryset.filter(privacy='followers')
            if target_user.followers.filter(id=requester.id).exists():
                followers_posts = followers_posts  # keep
            else:
                followers_posts = queryset.none()
            # Secret posts: not visible to others
            secret_posts = queryset.none()
            # Union
            queryset = public_posts | followers_posts
        else:
            # Anonymous user: only see public posts
            queryset = queryset.filter(privacy='public')

        return list(queryset.order_by('-created_at')[offset:offset+limit])