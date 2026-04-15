# users/services/user_image.py
from typing import List, Dict, Any, Tuple
from django.db import models
from django.db.models import Q
from feed.models.post import Post
from feed.services.media import MediaProcessingService
from users.models import User
from feed.models import Media, Reel
from stories.models import Story
from django.db import transaction
from typing import Optional
from users.models import User, UserImage
from users.services.user_follow import UserFollowService
import os
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from typing import Optional
from users.models import User, UserImage


class UserImageService:
    @staticmethod
    def get_visible_images(
        user: User, viewer: Optional[User], limit: int = 500
    ) -> List[UserImage]:
        """
        Return active images (both profile and cover) that are visible to the viewer.
        """
        queryset = user.images.filter(is_active=True)
        if not viewer:
            # Anonymous: only public images
            queryset = queryset.filter(privacy="public")
        else:
            if viewer == user:
                # Owner sees all their own images
                pass
            else:
                # Others: filter by privacy
                allowed = []
                for img in queryset:
                    if img.privacy == "public":
                        allowed.append(img)
                    elif img.privacy == "followers" and UserFollowService.is_following(
                        viewer, user
                    ):
                        allowed.append(img)
                return allowed[:limit]
        return list(queryset[:limit])

    """
    Service to gather all media items (post images/videos, reels, story media, user images)
    from a user, sorted by creation date, for a media grid.
    """

    @classmethod
    def get_user_media(
        cls,
        user: User,
        request=None,
        requester: Optional[User] = None,
        page: int = 1,
        page_size: int = 20,
        max_items: int = 500,
        media_type: Optional[str] = None,      # changed from content_type
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Return a list of media items (each as a dict) from the user,
        sorted by created_at descending, along with the total count.
        media_type can be 'image' or 'video' to filter by file type.
        """
        if not request:
            raise Exception("Request Not Provided For Build Uri")
        offset = (page - 1) * page_size

        # 1. Post media
        post_media_qs = Media.objects.filter(
            post__user=user, post__is_deleted=False
        ).order_by("-post__created_at", "order")
        post_media = list(post_media_qs[:max_items])

        # 2. Reels (always video)
        reels = list(
            Reel.objects.filter(user=user, is_deleted=False).order_by("-created_at")[:max_items]
        )

        # 3. Stories – already have story_type 'image' or 'video'
        stories = list(
            Story.objects.filter(
                user=user,
                is_active=True,
                expires_at__gt=models.F("expires_at"),
                story_type__in=["image", "video"],
            ).order_by("-created_at")[:max_items]
        )

        # 4. User images (always image)
        user_images_qs = UserImage.objects.filter(user=user, is_active=True)
        if requester and requester != user:
            user_images_qs = user_images_qs.filter(
                Q(privacy="public")
                | (Q(privacy="followers") & Q(user__followers__id=requester.id))
            )
        user_images = list(user_images_qs.order_by("-created_at")[:max_items])

        combined = []

        # Helper to guess if a file is an image or video (by extension or mime)
        def _get_file_type(file_field):
            if not file_field:
                return None
            name = file_field.name.lower()
            if name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                return 'image'
            if name.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm', '.mpeg')):
                return 'video'
            return None

        # --- Post media ---
        for media in post_media:
            file_type = _get_file_type(media.file)
            if not file_type:
                continue
            
            thumbnail_url = MediaProcessingService.get_video_thumbnail_url(media)
            combined.append({
                "type": "post_media",
                "url": request.build_absolute_uri(media.file.url) if media.file else None,
                "thumbnail": request.build_absolute_uri(thumbnail_url) if thumbnail_url else None,
                "created_at": media.content_object.created_at if isinstance(media.content_object, Post) else None,
                "content_id": media.content_object.id if isinstance(media.content_object, Post) else None,
                "content_type": "post",
                "media_order": media.order,
                "media_id": media.id,
                "media_format": file_type,          # 'image' or 'video'
            })

        # --- Reels (always video) ---
        for reel in reels:
            media_obj = reel.media.first()
            if media_obj and media_obj.file:
                thumbnail_url = MediaProcessingService.get_video_thumbnail_url(media_obj)
                
                combined.append({
                    "type": "reel",
                    "url": request.build_absolute_uri(media_obj.file.url),
                    "thumbnail": request.build_absolute_uri(thumbnail_url) if thumbnail_url else None,
                    "created_at": reel.created_at,
                    "content_id": reel.id,
                    "content_type": "reel",
                    "media_order": None,
                    "media_format": "video",
                })

        # --- Stories (use story_type) ---
        for story in stories:
            combined.append({
                "type": "story_media",
                "url": request.build_absolute_uri(story.media_url.url) if story.media_url else None,
                "thumbnail": None,
                "created_at": story.created_at,
                "content_id": story.id,
                "content_type": "story",
                "media_order": None,
                "media_format": story.story_type,   # 'image' or 'video'
            })

        # --- User images (always image) ---
        for user_image in user_images:
            combined.append({
                "type": "user_image",
                "url": request.build_absolute_uri(user_image.image.url) if user_image.image else None,
                "thumbnail": None,
                "created_at": user_image.created_at,
                "content_id": user_image.id,
                "content_type": "user_image",
                "media_order": None,
                "media_format": "image",
            })

        # Filter by media_type if provided
        if media_type:
            if media_type not in ('image', 'video'):
                raise ValueError("media_type must be 'image' or 'video'")
            combined = [item for item in combined if item.get('media_format') == media_type]

        # Sort by created_at descending
        combined.sort(key=lambda x: x["created_at"], reverse=True)

        total = len(combined)
        paginated = combined[offset : offset + page_size]

        return paginated, total

    def get_visible_image(
        user: User, image_type: str, viewer: Optional[User] = None
    ) -> Optional[UserImage]:
        active = UserImageService.get_active_image(user, image_type)
        if not active:
            return None
        if not viewer:
            # anonymous: only public images
            return active if active.privacy == "public" else None
        if viewer == user:
            return active
        if active.privacy == "public":
            return active
        if active.privacy == "followers" and UserFollowService.is_following(
            viewer, user
        ):
            return active
        return None

    @staticmethod
    def set_active_image(
        user: User,
        image_type: str,
        image_file,
        caption: str = "",
        privacy: str = "followers",
        crop_x: int = 0,
        crop_y: int = 0,
        crop_width: Optional[int] = None,
        crop_height: Optional[int] = None,
    ) -> UserImage:
        """
        Create a new image and set it as active for the given user and type.
        Deactivates any other active image of the same type.
        If crop parameters are provided, the image is cropped and resized.
        """
        with transaction.atomic():
            # Deactivate existing active image
            UserImage.objects.filter(
                user=user, image_type=image_type, is_active=True
            ).update(is_active=False)

            # Process the image (cropping, resizing, format conversion)
            processed_file = UserImageService._process_image(
                user,
                image_file,
                crop_x,
                crop_y,
                crop_width,
                crop_height,
                image_type,  # to know if profile (square) or cover (wider)
            )

            # Create new image
            image = UserImage.objects.create(
                user=user,
                image=processed_file,
                image_type=image_type,
                caption=caption,
                privacy=privacy,
                is_active=True,
            )
            return image

    @staticmethod
    def _process_image(
        user, image_file, crop_x, crop_y, crop_width, crop_height, image_type
    ):
        """
        Crop and resize the image.
        For profile pictures, we enforce a square (e.g., 500x500).
        For cover photos, we enforce a wide aspect ratio (e.g., 1500x500).
        """
        try:
            image_file.seek(0)
            img = Image.open(image_file)

            # If cropping is requested
            if crop_width and crop_height:
                img = img.crop(
                    (crop_x, crop_y, crop_x + crop_width, crop_y + crop_height)
                )

            # Convert to RGB if needed
            if img.mode in ("RGBA", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")

            # Resize based on image type
            if image_type == "profile":
                img.thumbnail((500, 500), Image.Resampling.LANCZOS)
            else:  # cover
                img.thumbnail((1500, 500), Image.Resampling.LANCZOS)

            # Save to buffer
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85)

            # Determine filename
            _, ext = os.path.splitext(image_file.name or "")
            ext = ext or ".jpg"
            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
            new_filename = f"{image_type}_{user.id}_{timestamp}{ext}"

            return ContentFile(buffer.getvalue(), name=new_filename)

        except Exception as e:
            raise Exception(f"Image processing failed: {str(e)}")

    @staticmethod
    def get_active_image(user: User, image_type: str) -> Optional[UserImage]:
        return user.images.filter(image_type=image_type, is_active=True).first()

    @staticmethod
    def get_active_image_url(
        image_type: str, build_url: bool = False, request=None
    ) -> Optional[str]:

        user_image: UserImage = UserImage.objects.filter(
            image_type=image_type, is_active=True
        ).first()
        if user_image and request and build_url:
            return request.build_absolute_uri(user_image.image.url)
        return user_image

    @staticmethod
    def remove_active_image(user: User, image_type: str) -> bool:
        active = UserImageService.get_active_image(user, image_type)
        if active:
            active.is_active = False
            active.save()
            return True
        return False

    @staticmethod
    def get_image_by_id(image_id: int) -> Optional[UserImage]:
        try:
            return UserImage.objects.get(id=image_id)
        except UserImage.DoesNotExist:
            return None
