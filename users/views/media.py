# users/views/media.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from users.serializers.user_image import (
    UserImageCreateSerializer,
    UserImageDisplaySerializer,
    UserImageMinimalSerializer,
)
from users.services.user_image import UserImageService
from users.models import User


class ProfilePictureUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
                 request={
            'multipart/form-data': UserImageCreateSerializer,
        },
        responses={200: UserImageDisplaySerializer},
        description="Upload or update the current user's profile picture.",
    )
    def post(self, request):
        # Add image_type to request data
        data = request.data.copy()
        data['image_type'] = 'profile'
        serializer = UserImageCreateSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            image = serializer.save()
            # Optionally return the image data
            display_serializer = UserImageDisplaySerializer(image, context={'request': request})
            return Response(display_serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CoverPhotoUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
                 request={
            'multipart/form-data': UserImageCreateSerializer,
        },
        responses={200: UserImageDisplaySerializer},
        description="Upload or update the current user's cover photo.",
    )
    def post(self, request):
        data = request.data.copy()
        data['image_type'] = 'cover'
        serializer = UserImageCreateSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            image = serializer.save()
            display_serializer = UserImageDisplaySerializer(image, context={'request': request})
            return Response(display_serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RemoveProfilePictureView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        responses={200: UserImageMinimalSerializer},
        description="Remove the current user's profile picture.",
    )
    def post(self, request):
        success = UserImageService.remove_active_image(request.user, 'profile')
        if not success:
            return Response({'error': 'No profile picture to remove'}, status=status.HTTP_400_BAD_REQUEST)
        # Optionally return the now-inactive image (or null)
        return Response({'message': 'Profile picture removed successfully'})


class RemoveCoverPhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        responses={200: UserImageMinimalSerializer},
        description="Remove the current user's cover photo.",
    )
    def post(self, request):
        success = UserImageService.remove_active_image(request.user, 'cover')
        if not success:
            return Response({'error': 'No cover photo to remove'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'Cover photo removed successfully'})


class GetProfilePictureView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        parameters=[OpenApiParameter(name='user_id', type=int, required=False)],
        responses={200: UserImageMinimalSerializer},
        description="Get the profile picture of a user (current if no user_id).",
    )
    def get(self, request, user_id=None):
        if user_id:
            user = get_object_or_404(User, id=user_id)
        else:
            user = request.user

        active = UserImageService.get_active_image(user, 'profile')
        if active:
            serializer = UserImageMinimalSerializer(active, context={'request': request})
            return Response(serializer.data)
        return Response({'message': 'No profile picture'}, status=status.HTTP_404_NOT_FOUND)


class GetCoverPhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["User Media"],
        parameters=[OpenApiParameter(name='user_id', type=int, required=False)],
        responses={200: UserImageMinimalSerializer},
        description="Get the cover photo of a user (current if no user_id).",
    )
    def get(self, request, user_id=None):
        if user_id:
            user = get_object_or_404(User, id=user_id)
        else:
            user = request.user

        active = UserImageService.get_active_image(user, 'cover')
        if active:
            serializer = UserImageMinimalSerializer(active, context={'request': request})
            return Response(serializer.data)
        return Response({'message': 'No cover photo'}, status=status.HTTP_404_NOT_FOUND)