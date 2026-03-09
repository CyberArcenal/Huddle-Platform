from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.core.files.storage import default_storage

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from django.db import transaction
from ..serializers.media import (
    ProfilePictureUploadSerializer,
    CoverPhotoUploadSerializer,
    RemoveProfilePictureSerializer,
    RemoveCoverPhotoSerializer,
)
from ..models import User
from rest_framework import serializers


# ----- New input serializer for ValidateImageUploadView -----
class ImageValidationInputSerializer(serializers.Serializer):
    image = serializers.ImageField(help_text="Image file to validate")


# ------------------------------------------------------------


class ProfilePictureUploadView(APIView):
    """View for uploading profile pictures"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ProfilePictureUploadSerializer,
        responses={200: {"type": "object"}},
        examples=[
            OpenApiExample(
                "Upload request",
                value={"profile_picture": "binary file data"},
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "message": "Profile picture uploaded successfully",
                    "user": {
                        "id": 1,
                        "username": "johndoe",
                        "profile_picture": "https://...",
                    },
                },
                response_only=True,
            ),
        ],
        description="Upload or update the current user's profile picture.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = ProfilePictureUploadSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                user = serializer.save()

                from ..serializers.user import UserProfileSerializer

                user_serializer = UserProfileSerializer(
                    user, context={"request": request}
                )

                return Response(
                    {
                        "message": "Profile picture uploaded successfully",
                        "user": user_serializer.data,
                    },
                    status=status.HTTP_200_OK,
                )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class CoverPhotoUploadView(APIView):
    """View for uploading cover photos"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=CoverPhotoUploadSerializer,
        responses={200: {"type": "object"}},
        examples=[
            OpenApiExample(
                "Upload request",
                value={"cover_photo": "binary file data"},
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "message": "Cover photo uploaded successfully",
                    "user": {
                        "id": 1,
                        "username": "johndoe",
                        "cover_photo": "https://...",
                    },
                },
                response_only=True,
            ),
        ],
        description="Upload or update the current user's cover photo.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = CoverPhotoUploadSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                user = serializer.save()

                from ..serializers.user import UserProfileSerializer

                user_serializer = UserProfileSerializer(
                    user, context={"request": request}
                )

                return Response(
                    {
                        "message": "Cover photo uploaded successfully",
                        "user": user_serializer.data,
                    },
                    status=status.HTTP_200_OK,
                )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class RemoveProfilePictureView(APIView):
    """View for removing profile picture"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=RemoveProfilePictureSerializer,
        responses={200: {"type": "object"}},
        description="Remove the current user's profile picture.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = RemoveProfilePictureSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                user = serializer.save()

                from ..serializers.user import UserProfileSerializer

                user_serializer = UserProfileSerializer(
                    user, context={"request": request}
                )

                return Response(
                    {
                        "message": "Profile picture removed successfully",
                        "user": user_serializer.data,
                    }
                )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class RemoveCoverPhotoView(APIView):
    """View for removing cover photo"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=RemoveCoverPhotoSerializer,
        responses={200: {"type": "object"}},
        description="Remove the current user's cover photo.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = RemoveCoverPhotoSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            try:
                user = serializer.save()

                from ..serializers.user import UserProfileSerializer

                user_serializer = UserProfileSerializer(
                    user, context={"request": request}
                )

                return Response(
                    {
                        "message": "Cover photo removed successfully",
                        "user": user_serializer.data,
                    }
                )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class GetProfilePictureView(APIView):
    """View for getting profile picture URL"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (optional, defaults to current)",
                required=False,
            ),
        ],
        responses={200: {"type": "object"}},
        description="Get the profile picture URL for a user.",
    )
    def get(self, request, user_id=None):
        try:
            from ..services.user import UserService

            if user_id:
                user = UserService.get_user_by_id(user_id)
            else:
                user = request.user

            if not user:
                return Response(
                    {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )

            profile_picture_url = None
            if user.profile_picture:
                request = self.request
                profile_picture_url = request.build_absolute_uri(
                    user.profile_picture.url
                )

            return Response(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "profile_picture_url": profile_picture_url,
                    "has_profile_picture": bool(user.profile_picture),
                }
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GetCoverPhotoView(APIView):
    """View for getting cover photo URL"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (optional, defaults to current)",
                required=False,
            ),
        ],
        responses={200: {"type": "object"}},
        description="Get the cover photo URL for a user.",
    )
    def get(self, request, user_id=None):
        try:
            from ..services.user import UserService

            if user_id:
                user = UserService.get_user_by_id(user_id)
            else:
                user = request.user

            if not user:
                return Response(
                    {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )

            cover_photo_url = None
            if user.cover_photo:
                request = self.request
                cover_photo_url = request.build_absolute_uri(user.cover_photo.url)

            return Response(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "cover_photo_url": cover_photo_url,
                    "has_cover_photo": bool(user.cover_photo),
                }
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ValidateImageUploadView(APIView):
    """View for validating image before upload"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ImageValidationInputSerializer,  # ✅ Now using dedicated serializer
        responses={200: {"type": "object"}},
        examples=[
            OpenApiExample(
                "Valid response",
                value={
                    "valid": True,
                    "filename": "photo.jpg",
                    "size": 102400,
                    "dimensions": {"width": 800, "height": 600},
                    "format": "JPEG",
                    "mime_type": "image/jpeg",
                },
                response_only=True,
            )
        ],
        description="Validate an image file before upload (checks size, dimensions, format).",
    )
    @transaction.atomic
    def post(self, request):
        serializer = ImageValidationInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        image_file = serializer.validated_data["image"]

        try:
            from PIL import Image
            import os

            max_size = 5 * 1024 * 1024  # 5MB
            if image_file.size > max_size:
                return Response(
                    {
                        "valid": False,
                        "error": f"Image size must be less than 5MB. Current size: {image_file.size / 1024 / 1024:.2f}MB",
                    }
                )

            try:
                image = Image.open(image_file)
                width, height = image.size
                format_name = image.format

                supported_formats = ["JPEG", "PNG", "GIF", "WEBP"]
                if format_name not in supported_formats:
                    return Response(
                        {
                            "valid": False,
                            "error": f'Image format {format_name} not supported. Must be one of: {", ".join(supported_formats)}',
                        }
                    )

                min_dimension = 100
                if width < min_dimension or height < min_dimension:
                    return Response(
                        {
                            "valid": False,
                            "error": f"Image must be at least {min_dimension}x{min_dimension} pixels. Current: {width}x{height}",
                        }
                    )

                max_dimension = 5000
                if width > max_dimension or height > max_dimension:
                    return Response(
                        {
                            "valid": False,
                            "warning": f"Image dimensions are large ({width}x{height}). It will be resized for optimal performance.",
                        }
                    )

                return Response(
                    {
                        "valid": True,
                        "filename": image_file.name,
                        "size": image_file.size,
                        "dimensions": {"width": width, "height": height},
                        "format": format_name,
                        "mime_type": image_file.content_type,
                    }
                )

            except Exception as img_error:
                return Response(
                    {"valid": False, "error": f"Invalid image file: {str(img_error)}"}
                )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
