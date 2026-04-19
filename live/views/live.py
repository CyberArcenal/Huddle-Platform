import logging
import traceback
from rest_framework.views import APIView, PermissionDenied
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import OpenApiResponse, extend_schema, OpenApiParameter
from django.shortcuts import get_object_or_404
from django.db import transaction

from core import settings
from global_utils.pagination import StandardResultsSetPagination
from live.services.live import LiveService
from live.serializers.live import (
    LiveStreamSerializer,
    LiveCreateSerializer,
    LiveJoinRequestSerializer,
    LiveParticipantSerializer,
)
from rest_framework import serializers
from live.models.live import LiveParticipant, LiveStream
from live.services.livekit import get_livekit_token

logger = logging.getLogger(__name__)


class LiveTokenResponseDataSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="LiveKit access token")
    url = serializers.CharField(help_text="LiveKit server URL")
    room_name = serializers.CharField(help_text="LiveKit room name")


class LiveTokenResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LiveTokenResponseDataSerializer(allow_null=True)


class StartLiveResponseDataSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="LiveKit access token")
    live_data = LiveStreamSerializer(help_text="Details of the created live stream")


class StartLiveResponse(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = StartLiveResponseDataSerializer()


class StartLiveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Live"], request=LiveCreateSerializer, responses={201: StartLiveResponse}
    )
    @transaction.atomic
    def post(self, request):
        serializer = LiveCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            live, token = LiveService.start_live(
                host=request.user, **serializer.validated_data
            )
            response = {
                "status": True,
                "message": "Live stream started.",
                "data": {
                    "token": token,
                    "live_data": LiveStreamSerializer(
                        live, context={"request": request}
                    ).data,
                },
            }

            return Response(response, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error starting live stream: {e}", exc_info=True)
            traceback.print_exc()
            return Response(
                {"status": False, "message": "Something went wrong."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class EndLiveResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()


class EndLiveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Live"], responses={200: EndLiveResponseSerializer})
    @transaction.atomic
    def post(self, request, live_id):
        live = get_object_or_404(LiveStream, id=live_id)
        try:
            LiveService.end_live(live, request.user)
            return Response({"status": True, "message": "Stream ended."})
        except Exception as e:
            return Response(
                {"status": False, "message": "Something went wrong."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class LiveStreamSerializerData(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = LiveStreamSerializer(many=True)


class ActiveLivesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LiveStreamSerializerData()


class ActiveLivesView(APIView):
    permission_classes = [AllowAny]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=["Live"],
        responses={200: ActiveLivesResponseSerializer},
        parameters=[
            OpenApiParameter(
                name="page", type=int, description="Page number", required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Results per page",
                required=False,
            ),
        ],
    )
    def get(self, request):
        try:
            lives = LiveService.get_active_streams(
                exclude_user=request.user if request.user.is_authenticated else None
            )
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(lives, request)

            serializer = LiveStreamSerializer(
                page, many=True, context={"request": request}
            )

            return paginator.get_paginated_response(serializer.data)
        except Exception as e:
            traceback.print_exc()
            return Response(
                {"status": False, "message": "Something went wrong."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class LiveDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LiveStreamSerializer()


class LiveDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Live"], responses={200: LiveDetailResponseSerializer})
    def get(self, request, live_id):
        try:
            user = request.user if request.user.is_authenticated else None
            live = LiveService.get_live_by_id(live_id, user)
            if not live:
                return Response(
                    {
                        "status": False,
                        "message": "Live stream not found or not accessible.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = LiveStreamSerializer(live, context={"request": request})
            response = {
                "status": True,
                "message": "Live stream details retrieved.",
                "data": serializer.data,
            }
            return Response(response)
        except Exception as e:
            traceback.print_exc()
            return Response(
                {"status": False, "message": "Something went wrong."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RequestJoinLiveViewResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LiveJoinRequestSerializer()


class RequestJoinLiveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Live"],
        request={"message": serializers.CharField(required=False)},
        responses={201: RequestJoinLiveViewResponseSerializer},
    )
    @transaction.atomic
    def post(self, request, live_id):
        live = get_object_or_404(LiveStream, id=live_id)
        message = request.data.get("message", "")
        try:
            req = LiveService.request_join(request.user, live, message)
            response = {
                "status": True,
                "message": "Join request submitted.",
                "data": LiveJoinRequestSerializer(req).data,
            }
            return Response(response, status=status.HTTP_201_CREATED)
        except Exception as e:
            traceback.print_exc()
            return Response(
                {"status": False, "message": "Something went wrong.", "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RespondToJoinRequestResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LiveJoinRequestSerializer()


class RespondToJoinRequestCreateSerializer(serializers.Serializer):
    approve = serializers.BooleanField(
        required=True, help_text="True to approve, False to reject"
    )


class RespondToJoinRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Live"],
        request=RespondToJoinRequestCreateSerializer,
        responses={200: RespondToJoinRequestResponseSerializer},
    )
    @transaction.atomic
    def post(self, request, request_id):
        approve = request.data.get("approve", False)
        try:
            req = LiveService.respond_to_request(request.user, request_id, approve)
            response = {
                "status": True,
                "message": f"Request {'approved' if approve else 'rejected'}.",
                "data": LiveJoinRequestSerializer(req).data,
            }
            return Response(response)
        except Exception as e:
            traceback.print_exc()
            return Response(
                {"status": False, "message": "Something went wrong.", "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )


class LiveParticipantsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = LiveParticipantSerializer(many=True)


class LiveParticipantsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Live"], responses={200: LiveParticipantsResponseSerializer})
    def get(self, request, live_id):
        try:
            live = get_object_or_404(LiveStream, id=live_id)
            # Check if user can see participants (public or already in stream)
            user = request.user if request.user.is_authenticated else None
            if live.is_private and (
                not user
                or (
                    user != live.host
                    and not LiveParticipant.objects.filter(
                        live=live, user=user
                    ).exists()
                )
            ):
                return Response(
                    {"status": False, "message": "Cannot view participants."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            participants = LiveService.get_participants(live)
            serializer = LiveParticipantSerializer(participants, many=True)
            response = {
                "status": True,
                "message": "Participants retrieved successfully.",
                "data": serializer.data,
            }
            return Response(response)
        except Exception as e:
            traceback.print_exc()
            return Response(
                {"status": False, "message": "Something went wrong.", "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )


class LeaveLiveViewResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()


class LeaveLiveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Live"], responses={200: LeaveLiveViewResponseSerializer})
    @transaction.atomic
    def post(self, request, live_id):
        live = get_object_or_404(LiveStream, id=live_id)
        success = LiveService.leave_live(request.user, live)
        if success:
            return Response({"status": True, "message": "Left the stream."})
        return Response(
            {"status": False, "message": "You are not in this stream."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class GetPendingRequestsResponseDataSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = LiveJoinRequestSerializer(many=True)


class GetPendingRequestsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = GetPendingRequestsResponseDataSerializer()


class PendingRequestsView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(tags=["Live"], responses={200: GetPendingRequestsResponseSerializer})
    def get(self, request, live_id):
        live = get_object_or_404(LiveStream, id=live_id)
        try:
            requests = LiveService.get_pending_requests(live, request.user)
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(requests, request)
            serializer = LiveJoinRequestSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        except PermissionDenied:
            return Response(
                {"status": False, "message": "Not authorized."},
                status=status.HTTP_403_FORBIDDEN,
            )


class LiveTokenView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Live"],
        operation_id="get_live_token",
        summary="Get LiveKit access token",
        description=(
            "Returns a LiveKit access token for the authenticated user to join the specified live stream. "
            "The user must be either the host or an approved participant."
        ),
        responses={
            200: OpenApiResponse(
                response=LiveTokenResponseSerializer,
                description="Token successfully generated.",
            ),
            403: OpenApiResponse(
                description="User is not authorized to join this stream."
            ),
            404: OpenApiResponse(description="Live stream not found."),
        },
    )
    def get(self, request, live_id):
        live = get_object_or_404(LiveStream, id=live_id)
        is_host = live.host == request.user
        is_participant = LiveParticipant.objects.filter(
            live=live, user=request.user, left_at__isnull=True
        ).exists()

        if not (is_host or is_participant):
            return Response(
                {
                    "status": False,
                    "message": "You are not authorized to join this stream.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        room_name = live.livekit_room or f"live_{live.id}"
        token = get_livekit_token(
            room_name, identity=f"user_{request.user.id}", name=request.user.username
        )
        ws_url = getattr(settings, 'LIVEKIT_WS_URL', 'ws://localhost:7880')

        return Response(
            {
                "status": True,
                "message": "Token generated successfully.",
                "data": {
                    "token": token,
                    "url": ws_url,
                    "room_name": room_name,
                },
            }
        )
