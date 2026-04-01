# users/views/media.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, serializers
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from users.serializers.user_image import (
    UserImageCreateSerializer,
    UserImageDisplaySerializer,
    UserImageMinimalSerializer,
)
from users.services.user_image import UserImageService
from users.models import User

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class UserImageUploadResponseData(serializers.Serializer):
    image = UserImageDisplaySerializer()


class UserImageUploadResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserImageUploadResponseData()


class UserImageRemoveResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class UserImageGetResponseData(serializers.Serializer):
    image = UserImageMinimalSerializer()


class UserImageGetResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserImageGetResponseData(allow_null=True)


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class ProfilePictureUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        request={
            'multipart/form-data': UserImageCreateSerializer,
        },
        responses={200: UserImageUploadResponseSerializer},
        description="Upload or update the current user's profile picture.",
    )
    def post(self, request):
        try:
            data = request.data.copy()
            data['image_type'] = 'profile'
            serializer = UserImageCreateSerializer(data=data, context={'request': request})
            if serializer.is_valid():
                image = serializer.save()
                display_serializer = UserImageDisplaySerializer(image, context={'request': request})
                return Response(
                    {
                        "status": True,
                        "message": "Profile picture uploaded successfully.",
                        "data": {"image": display_serializer.data},
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error uploading profile picture")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CoverPhotoUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        request={
            'multipart/form-data': UserImageCreateSerializer,
        },
        responses={200: UserImageUploadResponseSerializer},
        description="Upload or update the current user's cover photo.",
    )
    def post(self, request):
        try:
            data = request.data.copy()
            data['image_type'] = 'cover'
            serializer = UserImageCreateSerializer(data=data, context={'request': request})
            if serializer.is_valid():
                image = serializer.save()
                display_serializer = UserImageDisplaySerializer(image, context={'request': request})
                return Response(
                    {
                        "status": True,
                        "message": "Cover photo uploaded successfully.",
                        "data": {"image": display_serializer.data},
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error uploading cover photo")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RemoveProfilePictureView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        responses={200: UserImageRemoveResponseSerializer},
        description="Remove the current user's profile picture.",
    )
    def post(self, request):
        try:
            success = UserImageService.remove_active_image(request.user, 'profile')
            if not success:
                return Response(
                    {
                        "status": False,
                        "message": "No profile picture to remove",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    "status": True,
                    "message": "Profile picture removed successfully.",
                    "data": None,
                }
            )
        except Exception as e:
            logger.exception("Error removing profile picture")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RemoveCoverPhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        responses={200: UserImageRemoveResponseSerializer},
        description="Remove the current user's cover photo.",
    )
    def post(self, request):
        try:
            success = UserImageService.remove_active_image(request.user, 'cover')
            if not success:
                return Response(
                    {
                        "status": False,
                        "message": "No cover photo to remove",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    "status": True,
                    "message": "Cover photo removed successfully.",
                    "data": None,
                }
            )
        except Exception as e:
            logger.exception("Error removing cover photo")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GetProfilePictureView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        parameters=[OpenApiParameter(name='user_id', type=int, required=False)],
        responses={200: UserImageGetResponseSerializer},
        description="Get the profile picture of a user (current if no user_id).",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                user = get_object_or_404(User, id=user_id)
            else:
                user = request.user

            active = UserImageService.get_active_image(user, 'profile')
            if active:
                serializer = UserImageMinimalSerializer(active, context={'request': request})
                return Response(
                    {
                        "status": True,
                        "message": "Profile picture retrieved.",
                        "data": {"image": serializer.data},
                    }
                )
            return Response(
                {
                    "status": False,
                    "message": "No profile picture",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception("Error retrieving profile picture")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GetCoverPhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        parameters=[OpenApiParameter(name='user_id', type=int, required=False)],
        responses={200: UserImageGetResponseSerializer},
        description="Get the cover photo of a user (current if no user_id).",
    )
    def get(self, request, user_id=None):
        try:
            if user_id:
                user = get_object_or_404(User, id=user_id)
            else:
                user = request.user

            active = UserImageService.get_active_image(user, 'cover')
            if active:
                serializer = UserImageMinimalSerializer(active, context={'request': request})
                return Response(
                    {
                        "status": True,
                        "message": "Cover photo retrieved.",
                        "data": {"image": serializer.data},
                    }
                )
            return Response(
                {
                    "status": False,
                    "message": "No cover photo",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception("Error retrieving cover photo")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )