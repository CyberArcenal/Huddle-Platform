# serializers/media_serializer.py
from rest_framework import serializers
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image
import os

from ..models import User, UserActivity
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image

class NormalizedImageField(serializers.ImageField):
    
    """
    ImageField that ensures uploaded file has a sensible filename extension
    (detects format with Pillow and appends extension if missing) BEFORE
    running the normal ImageField validation.
    """

    FORMAT_EXT_MAP = {
        "JPEG": ".jpg",
        "JPG": ".jpg",
        "PNG": ".png",
        "GIF": ".gif",
        "WEBP": ".webp",
        "TIFF": ".tiff",
    }

    def _ensure_name_has_extension(self, uploaded_file):
        from PIL import Image
        # If name already has extension, nothing to do
        name = getattr(uploaded_file, "name", "") or ""
        base, ext = os.path.splitext(name)
        if ext:
            return

        # Try detect format from file bytes
        try:
            uploaded_file.seek(0)
            img = Image.open(uploaded_file)
            fmt = (img.format or "").upper()
            detected_ext = self.FORMAT_EXT_MAP.get(fmt)
            if detected_ext:
                uploaded_file.name = f"{base or 'upload'}{detected_ext}"
        except Exception:
            # fallback: give a safe default extension so validators won't fail
            uploaded_file.name = f"{base or 'upload'}.jpg"
        finally:
            uploaded_file.seek(0)

    def to_internal_value(self, data):
        # data is usually an InMemoryUploadedFile or TemporaryUploadedFile
        try:
            if hasattr(data, "name"):
                self._ensure_name_has_extension(data)
        except Exception:
            # don't break validation flow; let parent handle any remaining errors
            pass

        return super().to_internal_value(data)

class ProfilePictureUploadSerializer(serializers.Serializer):
    image_file = NormalizedImageField(
        required=True,
        allow_empty_file=False,
        help_text="Profile picture image file (JPG, PNG, GIF, WEBP)"
    )
    crop_x = serializers.IntegerField(required=False, min_value=0, default=0)
    crop_y = serializers.IntegerField(required=False, min_value=0, default=0)
    crop_width = serializers.IntegerField(required=False, min_value=50, allow_null=True)
    crop_height = serializers.IntegerField(
        required=False, min_value=50, allow_null=True
    )

    def validate_image_file(self, value):
        # verify image integrity
        try:
            value.seek(0)
            img = Image.open(value)
            img.verify()
        except Exception as e:
            raise serializers.ValidationError(f"Invalid image file: {e}")

        # reopen to inspect format
        value.seek(0)
        img = Image.open(value)
        fmt = (img.format or "").upper()

        # allowed formats
        allowed = {"JPEG", "JPG", "PNG", "GIF", "WEBP", "TIFF"}
        if fmt not in allowed:
            value.seek(0)
            raise serializers.ValidationError("Image must be in JPEG, PNG, GIF, or WEBP format")

        # max size check (keep this)
        max_size = 5 * 1024 * 1024
        if getattr(value, "size", 0) > max_size:
            value.seek(0)
            raise serializers.ValidationError("Image size must be less than 5MB.")

        # ensure filename has extension so validators won't fail
        name = getattr(value, "name", "") or ""
        base, current_ext = os.path.splitext(name)
        format_ext_map = {"JPEG": ".jpg", "JPG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp", "TIFF": ".tiff"}
        detected_ext = format_ext_map.get(fmt)
        if not current_ext and detected_ext:
            value.name = f"{base or 'upload'}{detected_ext}"

        value.seek(0)
        return value

    def _has_crop(self) -> bool:
        cd = self.validated_data
        return (
            cd.get("crop_width") is not None
            and cd.get("crop_height") is not None
            and cd.get("crop_width") >= 50
            and cd.get("crop_height") >= 50
        )

    def save(self, **kwargs):
        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError("Request context is required")
        user = request.user
        image_file = self.validated_data["image_file"]

        # detect extension from image_file.name (validate_image_file ensured it exists)
        _, file_ext = os.path.splitext(image_file.name or "")
        file_ext = file_ext or ".jpg"
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"profile_{user.id}_{timestamp}{file_ext}"

        try:
            if self._has_crop():
                image_file.seek(0)
                img = Image.open(image_file).convert("RGBA")
                crop_x = self.validated_data.get("crop_x", 0)
                crop_y = self.validated_data.get("crop_y", 0)
                crop_w = self.validated_data["crop_width"]
                crop_h = self.validated_data["crop_height"]

                cropped = img.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))

                if cropped.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", cropped.size, (255, 255, 255))
                    background.paste(cropped, mask=cropped.split()[-1])
                    cropped = background
                else:
                    cropped = cropped.convert("RGB")

                cropped.thumbnail((500, 500), Image.Resampling.LANCZOS)
                buffer = BytesIO()
                cropped.save(buffer, format="JPEG", quality=85)
                image_content = ContentFile(buffer.getvalue(), name=new_filename)

                if getattr(user, "profile_picture", None):
                    try:
                        user.profile_picture.delete(save=False)
                    except Exception:
                        pass
                user.profile_picture = image_content
            else:
                image_file.seek(0)
                content = ContentFile(image_file.read(), name=new_filename)
                if getattr(user, "profile_picture", None):
                    try:
                        user.profile_picture.delete(save=False)
                    except Exception:
                        pass
                user.profile_picture = content

            user.save()

            # optional: log activity (non‑blocking)
            try:
                UserActivity.objects.create(
                    user=user,
                    action="profile_picture_update",
                    description="User updated profile picture",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                    metadata={"filename": new_filename},
                )
            except Exception:
                pass

            return user

        except serializers.ValidationError:
            raise
        except Exception as e:
            raise serializers.ValidationError(f"Failed to process image: {str(e)}")


class CoverPhotoUploadSerializer(serializers.Serializer):
    image_file = NormalizedImageField(
        required=True,
        allow_empty_file=False,
        help_text="Cover photo image file (JPG, PNG, GIF, WEBP)"
    )

    def validate_image_file(self, value):
        # verify image integrity
        try:
            value.seek(0)
            img = Image.open(value)
            img.verify()
        except Exception as e:
            raise serializers.ValidationError(f"Invalid image file: {e}")

        value.seek(0)
        img = Image.open(value)
        fmt = (img.format or "").upper()
        allowed = {"JPEG", "JPG", "PNG", "GIF", "WEBP", "TIFF"}
        if fmt not in allowed:
            value.seek(0)
            raise serializers.ValidationError("Cover photo must be in JPEG, PNG, GIF, or WEBP format")

        # keep max size (10MB)
        max_size = 10 * 1024 * 1024
        if getattr(value, "size", 0) > max_size:
            value.seek(0)
            raise serializers.ValidationError("Cover photo must be less than 10MB.")

        # ensure filename extension exists
        name = getattr(value, "name", "") or ""
        base, current_ext = os.path.splitext(name)
        format_ext_map = {"JPEG": ".jpg", "JPG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp", "TIFF": ".tiff"}
        detected_ext = format_ext_map.get(fmt)
        if not current_ext and detected_ext:
            value.name = f"{base or 'upload'}{detected_ext}"

        value.seek(0)
        return value

    def save(self, **kwargs) -> User:
        """Save processed cover photo and return updated user"""
        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError("Request context is required")

        user = request.user
        image_file = self.validated_data["image_file"]

        # determine extension (validate_image_file ensured it exists)
        _, file_ext = os.path.splitext(image_file.name or "")
        file_ext = file_ext or ".jpg"
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"cover_{user.id}_{timestamp}{file_ext}"

        try:
            image_file.seek(0)
            img = Image.open(image_file)

            # Resize to recommended cover dimensions (max 1500x500)
            img.thumbnail((1500, 500), Image.Resampling.LANCZOS)

            # Convert to RGB if has alpha
            if img.mode in ("RGBA", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            image_content = ContentFile(buffer.getvalue(), name=new_filename)

            # remove old cover if exists
            if getattr(user, "cover_photo", None):
                try:
                    user.cover_photo.delete(save=False)
                except Exception:
                    pass

            user.cover_photo = image_content
            user.save()

            # log activity (non-blocking)
            try:
                UserActivity.objects.create(
                    user=user,
                    action="cover_photo_update",
                    description="User updated cover photo",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                    metadata={"filename": new_filename},
                )
            except Exception:
                pass

            return user

        except serializers.ValidationError:
            raise
        except Exception as e:
            raise serializers.ValidationError(f"Failed to process cover photo: {str(e)}")



class RemoveProfilePictureSerializer(serializers.Serializer):
    """Serializer for removing profile picture"""

    def save(self, **kwargs) -> User:
        """Remove profile picture"""
        request = self.context.get("request")
        user = request.user

        if user.profile_picture:
            user.profile_picture.delete(save=False)
            user.profile_picture = None
            user.save()

            # Log activity
            UserActivity.objects.create(
                user=user,
                action="profile_picture_removed",
                description="User removed profile picture",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )

        return user


class RemoveCoverPhotoSerializer(serializers.Serializer):
    """Serializer for removing cover photo"""

    def save(self, **kwargs) -> User:
        """Remove cover photo"""
        request = self.context.get("request")
        user = request.user

        if user.cover_photo:
            user.cover_photo.delete(save=False)
            user.cover_photo = None
            user.save()

            # Log activity
            UserActivity.objects.create(
                user=user,
                action="cover_photo_removed",
                description="User removed cover photo",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )

        return user
    
    
    






