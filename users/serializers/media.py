# serializers/media_serializer.py
from rest_framework import serializers
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image
import os
from typing import Dict, Any, Tuple, Optional

from ..models import User, UserActivity


class ProfilePictureUploadSerializer(serializers.Serializer):
    """Serializer for uploading profile pictures"""
    
    image = serializers.ImageField(
        required=True,
        max_length=100,
        allow_empty_file=False,
        help_text="Profile picture image file (JPG, PNG, GIF)"
    )
    crop_x = serializers.IntegerField(required=False, min_value=0, default=0)
    crop_y = serializers.IntegerField(required=False, min_value=0, default=0)
    crop_width = serializers.IntegerField(required=False, min_value=50)
    crop_height = serializers.IntegerField(required=False, min_value=50)
    
    def validate_image(self, value):
        """Validate uploaded image"""
        # Check file size (max 5MB)
        max_size = 5 * 1024 * 1024  # 5MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"Image size must be less than 5MB. Current size: {value.size / 1024 / 1024:.2f}MB"
            )
        
        # Check image dimensions
        try:
            image = Image.open(value)
            width, height = image.size
            
            # Minimum dimensions
            if width < 100 or height < 100:
                raise serializers.ValidationError(
                    f"Image must be at least 100x100 pixels. Current: {width}x{height}"
                )
            
            # Maximum dimensions (to prevent extremely large images)
            if width > 5000 or height > 5000:
                raise serializers.ValidationError(
                    f"Image dimensions cannot exceed 5000x5000 pixels. Current: {width}x{height}"
                )
            
            # Check format
            if image.format not in ['JPEG', 'PNG', 'GIF', 'WEBP']:
                raise serializers.ValidationError(
                    "Image must be in JPEG, PNG, GIF, or WEBP format"
                )
            
            return value
            
        except Exception as e:
            raise serializers.ValidationError(f"Invalid image file: {str(e)}")
    
    def save(self, **kwargs) -> User:
        """Save profile picture"""
        request = self.context.get('request')
        user = request.user
        image = self.validated_data['image']
        
        # Generate unique filename
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        file_name, file_ext = os.path.splitext(image.name)
        new_filename = f"profile_{user.id}_{timestamp}{file_ext}"
        
        # Process image if crop parameters provided
        if all(k in self.validated_data for k in ['crop_x', 'crop_y', 'crop_width', 'crop_height']):
            try:
                # Open and crop image
                img = Image.open(image)
                cropped = img.crop((
                    self.validated_data['crop_x'],
                    self.validated_data['crop_y'],
                    self.validated_data['crop_x'] + self.validated_data['crop_width'],
                    self.validated_data['crop_y'] + self.validated_data['crop_height']
                ))
                
                # Convert to RGB if necessary
                if cropped.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', cropped.size, (255, 255, 255))
                    background.paste(cropped, mask=cropped.split()[-1])
                    cropped = background
                
                # Resize to optimal profile picture size (500x500)
                cropped.thumbnail((500, 500), Image.Resampling.LANCZOS)
                
                # Save cropped image
                from io import BytesIO
                buffer = BytesIO()
                cropped.save(buffer, format='JPEG', quality=85)
                image_file = ContentFile(buffer.getvalue(), name=new_filename)
                
                # Update user profile picture
                if user.profile_picture:
                    user.profile_picture.delete(save=False)
                
                user.profile_picture = image_file
                
            except Exception as e:
                raise serializers.ValidationError(f"Failed to process image: {str(e)}")
        else:
            # Save original image
            user.profile_picture = image
        
        user.save()
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            action='profile_picture_update',
            description='User updated profile picture',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            metadata={'filename': new_filename}
        )
        
        return user


class CoverPhotoUploadSerializer(serializers.Serializer):
    """Serializer for uploading cover photos"""
    
    image = serializers.ImageField(
        required=True,
        max_length=100,
        allow_empty_file=False,
        help_text="Cover photo image file (JPG, PNG)"
    )
    
    def validate_image(self, value):
        """Validate cover photo"""
        # Check file size (max 10MB for cover photos)
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"Cover photo must be less than 10MB. Current size: {value.size / 1024 / 1024:.2f}MB"
            )
        
        # Check image dimensions (recommended cover photo size)
        try:
            image = Image.open(value)
            width, height = image.size
            
            # Minimum dimensions for cover photo
            if width < 800 or height < 200:
                raise serializers.ValidationError(
                    f"Cover photo must be at least 800x200 pixels. Current: {width}x{height}"
                )
            
            # Aspect ratio recommendation
            aspect_ratio = width / height
            if aspect_ratio < 2 or aspect_ratio > 4:
                # Warn but don't fail - different platforms have different requirements
                pass
            
            return value
            
        except Exception as e:
            raise serializers.ValidationError(f"Invalid image file: {str(e)}")
    
    def save(self, **kwargs) -> User:
        """Save cover photo"""
        request = self.context.get('request')
        user = request.user
        image = self.validated_data['image']
        
        # Generate unique filename
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        file_name, file_ext = os.path.splitext(image.name)
        new_filename = f"cover_{user.id}_{timestamp}{file_ext}"
        
        # Process image for optimal cover photo size
        try:
            img = Image.open(image)
            
            # Resize to optimal cover photo dimensions (1500x500)
            img.thumbnail((1500, 500), Image.Resampling.LANCZOS)
            
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            
            # Save processed image
            from io import BytesIO
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            image_file = ContentFile(buffer.getvalue(), name=new_filename)
            
            # Update user cover photo
            if user.cover_photo:
                user.cover_photo.delete(save=False)
            
            user.cover_photo = image_file
            
        except Exception as e:
            raise serializers.ValidationError(f"Failed to process cover photo: {str(e)}")
        
        user.save()
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            action='cover_photo_update',
            description='User updated cover photo',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            metadata={'filename': new_filename}
        )
        
        return user


class RemoveProfilePictureSerializer(serializers.Serializer):
    """Serializer for removing profile picture"""
    
    def save(self, **kwargs) -> User:
        """Remove profile picture"""
        request = self.context.get('request')
        user = request.user
        
        if user.profile_picture:
            user.profile_picture.delete(save=False)
            user.profile_picture = None
            user.save()
            
            # Log activity
            UserActivity.objects.create(
                user=user,
                action='profile_picture_removed',
                description='User removed profile picture',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
        
        return user


class RemoveCoverPhotoSerializer(serializers.Serializer):
    """Serializer for removing cover photo"""
    
    def save(self, **kwargs) -> User:
        """Remove cover photo"""
        request = self.context.get('request')
        user = request.user
        
        if user.cover_photo:
            user.cover_photo.delete(save=False)
            user.cover_photo = None
            user.save()
            
            # Log activity
            UserActivity.objects.create(
                user=user,
                action='cover_photo_removed',
                description='User removed cover photo',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
        
        return user