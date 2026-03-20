import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.core.files.storage import default_storage

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from django.db import transaction

from users.serializers.user import UserProfileSerializer
from users.services.user import UserService
from ..serializers.media import (
    ProfilePictureUploadSerializer,
    CoverPhotoUploadSerializer,
    RemoveProfilePictureSerializer,
    RemoveCoverPhotoSerializer,
)
from ..models import User
from rest_framework import serializers
from rest_framework import serializers
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiTypes,
    OpenApiResponse,
)


# ----- New input serializer for ValidateImageUploadView -----
class ImageValidationInputSerializer(serializers.Serializer):
    image = serializers.ImageField(help_text="Image file to validate")


# ------------------------------------------------------------


from rest_framework import status, permissions, serializers
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
)

from rest_framework import status, permissions, serializers
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
)


class ProfilePictureUploadResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = UserProfileSerializer(read_only=True)


class ValidationErrorResponseSerializer(serializers.Serializer):
    errors = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField())
    )


logger = logging.getLogger(__name__)


class ProfilePictureUploadView(APIView):
    """View for uploading profile pictures"""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["User Media"],
        
        request=ProfilePictureUploadSerializer,
        responses={
            200: OpenApiResponse(
                response=ProfilePictureUploadResponseSerializer,
                description="Profile picture uploaded successfully",
            ),
            400: OpenApiResponse(
                response=ValidationErrorResponseSerializer,
                description="Validation errors or bad request",
            ),
        },
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
        logger.debug(f"Incoming post: {request.data}")
        serializer = ProfilePictureUploadSerializer(
            data=request.data, context={"request": request}
        )

        if not serializer.is_valid(raise_exception=True):
            error_payload = {"errors": serializer.errors}
            return Response(
                ValidationErrorResponseSerializer(error_payload).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = serializer.save()

            # Use the existing UserProfileSerializer to produce the nested user object
            # user_data = UserProfileSerializer(user, context={"request": request}).data

            response_payload = {
                "message": "Profile picture uploaded successfully",
                "user": user,
            }

            response_serializer = ProfilePictureUploadResponseSerializer(
                response_payload, context={"request": request}
            )
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.debug(e)
            error_payload = {"errors": {"non_field_errors": [str(e)]}}
            return Response(
                ValidationErrorResponseSerializer(error_payload).data,
                status=status.HTTP_400_BAD_REQUEST,
            )


class CoverPhotoUploadResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = UserProfileSerializer(read_only=True)


class ValidationErrorResponseSerializer(serializers.Serializer):
    errors = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField())
    )


class CoverPhotoUploadView(APIView):
    """View for uploading cover photos"""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["User Media"],
        
        request=CoverPhotoUploadSerializer,
        responses={
            200: OpenApiResponse(
                response=CoverPhotoUploadResponseSerializer,
                description="Cover photo uploaded successfully",
            ),
            400: OpenApiResponse(
                response=ValidationErrorResponseSerializer,
                description="Validation errors or bad request",
            ),
        },
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
        logger.debug(f"Incoming post: {request.data}")
        serializer = CoverPhotoUploadSerializer(
            data=request.data, context={"request": request}
        )

        if not serializer.is_valid(raise_exception=True):
            error_payload = {"errors": serializer.errors}
            return Response(
                ValidationErrorResponseSerializer(error_payload).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = serializer.save()

            # Use the existing UserProfileSerializer to produce the nested user object
            # user_data = UserProfileSerializer(user, context={"request": request}).data

            response_payload = {
                "message": "Cover photo uploaded successfully",
                "user": user,
            }

            return Response(
                CoverPhotoUploadResponseSerializer(response_payload).data,
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.debug(e)
            error_payload = {"errors": {"non_field_errors": [str(e)]}}
            return Response(
                ValidationErrorResponseSerializer(error_payload).data,
                status=status.HTTP_400_BAD_REQUEST,
            )


class RemoveProfilePictureResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = UserProfileSerializer(read_only=True)


class ValidationErrorResponseSerializer(serializers.Serializer):
    errors = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField())
    )


class RemoveProfilePictureView(APIView):
    """View for removing profile picture"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        
        request=RemoveProfilePictureSerializer,
        responses={
            200: OpenApiResponse(
                response=RemoveProfilePictureResponseSerializer,
                description="Profile picture removed successfully",
            ),
            400: OpenApiResponse(
                response=ValidationErrorResponseSerializer,
                description="Validation errors or bad request",
            ),
        },
        description="Remove the current user's profile picture.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = RemoveProfilePictureSerializer(
            data=request.data, context={"request": request}
        )

        if not serializer.is_valid():
            error_payload = {"errors": serializer.errors}
            return Response(
                ValidationErrorResponseSerializer(error_payload).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = serializer.save()

            response_payload = {
                "message": "Profile picture removed successfully",
                "user": user,
            }

            return Response(
                RemoveProfilePictureResponseSerializer(response_payload).data,
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            error_payload = {"errors": {"non_field_errors": [str(e)]}}
            return Response(
                ValidationErrorResponseSerializer(error_payload).data,
                status=status.HTTP_400_BAD_REQUEST,
            )


class RemoveCoverPhotoResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = UserProfileSerializer(read_only=True)


class ValidationErrorResponseSerializer(serializers.Serializer):
    errors = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField())
    )


class RemoveCoverPhotoView(APIView):
    """View for removing cover photo"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        
        request=RemoveCoverPhotoSerializer,
        responses={
            200: OpenApiResponse(
                response=RemoveCoverPhotoResponseSerializer,
                description="Cover photo removed successfully",
            ),
            400: OpenApiResponse(
                response=ValidationErrorResponseSerializer,
                description="Validation errors or bad request",
            ),
        },
        description="Remove the current user's cover photo.",
    )
    @transaction.atomic
    def post(self, request):
        serializer = RemoveCoverPhotoSerializer(
            data=request.data, context={"request": request}
        )

        if not serializer.is_valid():
            error_payload = {"errors": serializer.errors}
            return Response(
                ValidationErrorResponseSerializer(error_payload).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = serializer.save()

            response_payload = {
                "message": "Cover photo removed successfully",
                "user": user,
            }

            return Response(
                RemoveCoverPhotoResponseSerializer(response_payload).data,
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            error_payload = {"errors": {"non_field_errors": [str(e)]}}
            return Response(
                ValidationErrorResponseSerializer(error_payload).data,
                status=status.HTTP_400_BAD_REQUEST,
            )


class ProfilePictureResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    profile_picture_url = serializers.CharField(allow_null=True)
    has_profile_picture = serializers.BooleanField()


class GetProfilePictureView(APIView):
    """View for getting profile picture URL"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="User ID (optional, defaults to current)",
                required=False,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ProfilePictureResponseSerializer,
                description="Profile picture details of the user",
            ),
            404: OpenApiResponse(description="User not found"),
            400: OpenApiResponse(description="Bad request"),
        },
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


class GetCoverPhotoResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    cover_photo_url = serializers.CharField(allow_null=True)
    has_cover_photo = serializers.BooleanField()


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class GetCoverPhotoView(APIView):
    """View for getting cover photo URL"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="User ID (optional, defaults to current)",
                required=False,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=GetCoverPhotoResponseSerializer,
                description="Cover photo details for the user",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer, description="User not found"
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer, description="Bad request"
            ),
        },
        description="Get the cover photo URL for a user.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                user = UserService.get_user_by_id(user_id)
            else:
                user = request.user

            if not user:
                return Response(
                    ErrorResponseSerializer({"error": "User not found"}).data,
                    status=status.HTTP_404_NOT_FOUND,
                )

            cover_photo_url = None
            if getattr(user, "cover_photo", None):
                cover_photo_url = request.build_absolute_uri(user.cover_photo.url)

            payload = {
                "user_id": user.id,
                "username": user.username,
                "cover_photo_url": cover_photo_url,
                "has_cover_photo": bool(getattr(user, "cover_photo", None)),
            }

            return Response(
                GetCoverPhotoResponseSerializer(payload).data, status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                ErrorResponseSerializer({"error": str(e)}).data,
                status=status.HTTP_400_BAD_REQUEST,
            )