from feed.models import Post
from users.models import User


class FeedService:
    """Service for managing user feeds (e.g., removing/adding posts)."""

    @staticmethod
    def remove_post_from_feeds(post: Post):
        """
        Remove a post from all followers' feeds.
        In production, this would involve deleting cache entries or updating feed tables.
        """
        # Example: get all followers of the post author
        followers = post.user.followers.all()  # assuming reverse relation exists
        for follower in followers:
            # Simulate removal from follower's feed (e.g., delete from cache)
            print(f"Removing post {post.id} from {follower.username}'s feed")
            # In real code: cache.delete(f"feed:{follower.id}:{post.id}")
            pass

    @staticmethod
    def add_post_to_feeds(post: Post):
        """
        Add a post back to followers' feeds (e.g., after restoration).
        """
        followers = post.user.followers.all()
        for follower in followers:
            print(f"Adding post {post.id} to {follower.username}'s feed")
            # In real code: cache.set(f"feed:{follower.id}:{post.id}", post)
            pass