from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from events.serializers.event import EventListSerializer
from events.serializers.event_attendance import (
    EventAttendanceWithUserSerializer,
    UserAttendanceStatisticsSerializer,
)
from global_utils.pagination import EventsPagination

from ..models import Event, EventAttendance
from ..serializers import (
    EventAttendanceSerializer,
    EventAttendanceCreateSerializer,
    EventAttendanceUpdateSerializer,
)
from ..services import EventAttendanceService, EventService
from users.models import User
from groups.services import GroupMemberService
from rest_framework import serializers
from events.serializers.event_attendance import EventAttendanceWithUserSerializer

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper to wrap paginated data
# ----------------------------------------------------------------------
def wrap_paginated_attendance(paginator, page, request, serializer_class):
    """
    Construct a paginated data dict that matches the expected structure.
    """
    serializer = serializer_class(page, many=True, context={'request': request})
    data = {
        'page': paginator.page.number,
        'hasNext': paginator.page.has_next(),
        'hasPrev': paginator.page.has_previous(),
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': serializer.data,
    }
    return data


# ----------------------------------------------------------------------
# Input serializers
# ----------------------------------------------------------------------
class RSVPInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["going", "maybe", "declined"], default="going", help_text="RSVP status"
    )


class UpdateStatusInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["going", "maybe", "declined"],
        required=True,
        help_text="New RSVP status",
    )


class SendRemindersInputSerializer(serializers.Serializer):
    hours_before = serializers.IntegerField(
        default=24, min_value=1, help_text="Hours before event to send reminder"
    )


# ----------------------------------------------------------------------
# Response serializers
# ----------------------------------------------------------------------

class PaginatedEventAttendanceWithUserData(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = EventAttendanceWithUserSerializer(many=True)


class EventAttendanceListResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedEventAttendanceWithUserData()


class EventAttendanceCreateResponseData(serializers.Serializer):
    attendance = EventAttendanceSerializer()


class EventAttendanceCreateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventAttendanceCreateResponseData()


class EventAttendanceDetailResponseData(serializers.Serializer):
    attendance = EventAttendanceSerializer()


class EventAttendanceDetailResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventAttendanceDetailResponseData()


class EventAttendanceUpdateResponseData(serializers.Serializer):
    attendance = EventAttendanceSerializer()


class EventAttendanceUpdateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = EventAttendanceUpdateResponseData()


class EventAttendanceDeleteResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = None


class PaginatedEventListData(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrev = serializers.BooleanField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = EventListSerializer(many=True)


class UserEventsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaginatedEventListData()


class UserAttendanceStatisticsResponseData(serializers.Serializer):
    statistics = UserAttendanceStatisticsSerializer()


class UserAttendanceStatisticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = UserAttendanceStatisticsResponseData()


class MutualAttendeeUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    name = serializers.CharField()


class MutualAttendeeSerializer(serializers.Serializer):
    user = MutualAttendeeUserSerializer()
    is_following = serializers.BooleanField()
    is_followed_by = serializers.BooleanField()
    is_mutual = serializers.BooleanField()


class MutualAttendeesResponseData(serializers.Serializer):
    attendees = MutualAttendeeSerializer(many=True)


class MutualAttendeesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = MutualAttendeesResponseData()


class AttendanceTrendData(serializers.Serializer):
    hour = serializers.DateTimeField()
    count = serializers.IntegerField()


class AttendanceTrendResponseData(serializers.Serializer):
    trend = AttendanceTrendData(many=True)


class AttendanceTrendResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = AttendanceTrendResponseData()


class SendRemindersResponseData(serializers.Serializer):
    event_id = serializers.IntegerField()
    hours_before = serializers.IntegerField()
    reminders_sent = serializers.IntegerField()
    attendees_to_remind = serializers.ListField(child=serializers.DictField())


class SendRemindersResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = SendRemindersResponseData()


# -------------------------------
# Input / Response Serializers
# -------------------------------

class AttendanceApprovalInputSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["approve", "reject"],
        help_text="Action to perform on attendee"
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional reason for rejection"
    )


class AttendanceApprovalResponseData(serializers.Serializer):
    attendance = EventAttendanceSerializer()
    reason = serializers.CharField(required=False, allow_blank=True)


class AttendanceApprovalResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = AttendanceApprovalResponseData()


# -------------------------------
# View
# -------------------------------
class EventAttendanceApprovalView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        request=AttendanceApprovalInputSerializer,
        responses={200: AttendanceApprovalResponseSerializer},
        examples=[
            OpenApiExample(
                "Approve attendee",
                value={"action": "approve"},
                request_only=True,
            ),
            OpenApiExample(
                "Reject attendee with reason",
                value={"action": "reject", "reason": "Capacity full"},
                request_only=True,
            ),
            OpenApiExample(
                "Approval response",
                value={
                    "status": True,
                    "message": "Attendance approved.",
                    "data": {
                        "attendance": {
                            "id": 12,
                            "event": 5,
                            "user": 7,
                            "status": "going",
                            "joined_at": "2026-04-02T12:34:56Z",
                        },
                        "reason": ""
                    },
                },
                response_only=True,
            ),
        ],
        description="Approve or reject an attendee for an event. Only the organizer can perform this action.",
    )
    @transaction.atomic
    def post(self, request, event_id, user_id):
        try:
            event = get_object_or_404(Event, id=event_id)
            if event.organizer != request.user:
                return Response(
                    {"status": False, "message": "Only the organizer can approve/reject attendees", "data": None},
                    status=status.HTTP_403_FORBIDDEN,
                )

            user = get_object_or_404(User, id=user_id)
            attendance = EventAttendance.objects.filter(event=event, user=user).first()
            if not attendance:
                return Response(
                    {"status": False, "message": "Attendance record not found", "data": None},
                    status=status.HTTP_404_NOT_FOUND,
                )

            serializer = AttendanceApprovalInputSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            action = serializer.validated_data["action"]
            reason = serializer.validated_data.get("reason", "")

            if action == "approve":
                attendance.status = "going"
                message = "Attendance approved."
            elif action == "reject":
                attendance.status = "declined"
                message = "Attendance rejected."

            attendance.save()
            data = EventAttendanceSerializer(attendance, context={"request": request}).data
            return Response(
                {"status": True, "message": message, "data": {"attendance": data, "reason": reason}},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Error approving/rejecting attendance")
            return Response(
                {"status": False, "message": "Something went wrong.", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EventAttendanceSearchView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        parameters=[
            OpenApiParameter(name="search", type=str, description="Search by username or name", required=False),
            OpenApiParameter(name="personality", type=str, description="Filter by MBTI personality type", required=False),
            OpenApiParameter(name="sort", type=str, description="Sort field (joined_at, name, capability_score)", required=False),
            OpenApiParameter(name="friendsOnly", type=bool, description="Filter to only friends", required=False),
            OpenApiParameter(name="page", type=int, description="Page number", required=False),
            OpenApiParameter(name="page_size", type=int, description="Results per page", required=False),
        ],
        responses={200: EventAttendanceListResponseSerializer},
        description="Search and filter attendees for an event.",
    )
    def get(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)
            has_access, message = EventService.check_user_access(event, request.user)
            if not has_access:
                return Response(
                    {"status": False, "message": message, "data": None},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Extract query params
            search = request.query_params.get("search")
            personality = request.query_params.get("personality")
            sort = request.query_params.get("sort")
            friends_only = request.query_params.get("friendsOnly") in ["true", "1"]

            # Service layer handles filtering logic
            attendees = EventAttendanceService.search_event_attendees(
                event=event,
                search=search,
                personality=personality,
                sort=sort,
                friends_only=friends_only,
                user=request.user,
            )

            paginator = EventsPagination()
            page = paginator.paginate_queryset(attendees, request)
            paginated_data = wrap_paginated_attendance(
                paginator, page, request, EventAttendanceWithUserSerializer
            )

            return Response(
                {"status": True, "message": "Attendees retrieved.", "data": paginated_data}
            )
        except Exception as e:
            logger.exception("Error searching attendees for event %s", event_id)
            return Response(
                {"status": False, "message": "Something went wrong.", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EventAttendanceListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                description="Filter by status (going, maybe, declined)",
                required=False,
            ),
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
        responses={200: EventAttendanceListResponseSerializer},
        description="List all attendees for an event, optionally filtered by status.",
    )
    def get(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)
            has_access, message = EventService.check_user_access(event, request.user)
            if not has_access:
                return Response(
                    {
                        "status": False,
                        "message": message,
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            status_filter = request.query_params.get("status")
            attendees = EventAttendanceService.get_event_attendees(
                event=event, status=status_filter
            )

            paginator = EventsPagination()
            page = paginator.paginate_queryset(attendees, request)
            paginated_data = wrap_paginated_attendance(
                paginator, page, request, EventAttendanceWithUserSerializer
            )

            return Response(
                {
                    "status": True,
                    "message": "Attendees retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error listing attendees for event %s", event_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Event Attendance"],
        request=EventAttendanceCreateSerializer,
        responses={201: EventAttendanceCreateResponseSerializer},
        examples=[
            OpenApiExample(
                "RSVP request", value={"status": "going"}, request_only=True
            ),
            OpenApiExample(
                "RSVP response",
                value={
                    "status": True,
                    "message": "RSVP successful.",
                    "data": {
                        "attendance": {
                            "id": 1,
                            "event": 1,
                            "user": 5,
                            "status": "going",
                            "joined_at": "2025-03-07T12:34:56Z",
                        }
                    },
                },
                response_only=True,
            ),
        ],
        description="RSVP to an event (create attendance).",
    )
    @transaction.atomic
    def post(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)
            data = request.data.copy()
            data["event"] = event.id
            serializer = EventAttendanceCreateSerializer(
                data=data, context={"request": request}
            )
            if serializer.is_valid():
                attendance = serializer.save()
                response_data = EventAttendanceSerializer(
                    attendance, context={"request": request}
                ).data
                return Response(
                    {
                        "status": True,
                        "message": "RSVP successful.",
                        "data": {"attendance": response_data},
                    },
                    status=status.HTTP_201_CREATED,
                )
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error creating RSVP for event %s", event_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EventAttendanceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, event_id, user_id=None):
        event = get_object_or_404(Event, id=event_id)
        if user_id is None:
            user = self.request.user
        else:
            user = get_object_or_404(User, id=user_id)
        attendance = EventAttendanceService.get_attendance(event, user)
        if not attendance:
            raise NotFound("Attendance record not found")
        return attendance

    @extend_schema(
        tags=["Event Attendance"],
        responses={200: EventAttendanceDetailResponseSerializer},
        description="Retrieve a specific attendance record.",
    )
    def get(self, request, event_id, user_id=None):
        try:
            attendance = self.get_object(event_id, user_id)
            if attendance.user != request.user and attendance.event.organizer != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You don't have permission to view this attendance",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            data = EventAttendanceSerializer(attendance, context={"request": request}).data
            return Response(
                {
                    "status": True,
                    "message": "Attendance record retrieved.",
                    "data": {"attendance": data},
                }
            )
        except NotFound as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception("Error retrieving attendance")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Event Attendance"],
        request=EventAttendanceUpdateSerializer,
        responses={200: EventAttendanceUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update status", value={"status": "maybe"}, request_only=True
            )
        ],
        description="Update attendance status (full update).",
    )
    @transaction.atomic
    def put(self, request, event_id, user_id=None):
        try:
            attendance = self.get_object(event_id, user_id)
            if attendance.user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only update your own attendance",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = EventAttendanceUpdateSerializer(
                attendance, data=request.data, partial=False, context={"request": request}
            )
            if serializer.is_valid():
                attendance = serializer.save()
                data = EventAttendanceSerializer(attendance, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Attendance updated.",
                        "data": {"attendance": data},
                    }
                )
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error updating attendance")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Event Attendance"],
        request=EventAttendanceUpdateSerializer,
        responses={200: EventAttendanceUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update status", value={"status": "declined"}, request_only=True
            )
        ],
        description="Partially update attendance status.",
    )
    def patch(self, request, event_id, user_id=None):
        try:
            attendance = self.get_object(event_id, user_id)
            if attendance.user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only update your own attendance",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = EventAttendanceUpdateSerializer(
                attendance, data=request.data, partial=True, context={"request": request}
            )
            if serializer.is_valid():
                attendance = serializer.save()
                data = EventAttendanceSerializer(attendance, context={"request": request}).data
                return Response(
                    {
                        "status": True,
                        "message": "Attendance partially updated.",
                        "data": {"attendance": data},
                    }
                )
            return Response(
                {
                    "status": False,
                    "message": "Validation error.",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error patching attendance")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Event Attendance"],
        responses={204: EventAttendanceDeleteResponseSerializer},
        description="Remove attendance (un‑RSVP).",
    )
    @transaction.atomic
    def delete(self, request, event_id, user_id=None):
        try:
            attendance = self.get_object(event_id, user_id)
            if attendance.user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only remove your own attendance",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            EventAttendanceService.remove_attendance(attendance.event, attendance.user)
            return Response(
                {
                    "status": True,
                    "message": "Attendance removed.",
                    "data": None,
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error deleting attendance")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EventRSVPView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        request=RSVPInputSerializer,
        responses={201: EventAttendanceCreateResponseSerializer},
        examples=[
            OpenApiExample("RSVP request", value={"status": "going"}, request_only=True)
        ],
        description="RSVP to an event (create or update attendance).",
    )
    @transaction.atomic
    def post(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)
            serializer = RSVPInputSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            status = serializer.validated_data["status"]
            created, attendance = EventAttendanceService.rsvp_to_event(
                event=event, user=request.user, status=status
            )
            response_data = EventAttendanceSerializer(
                attendance, context={"request": request}
            ).data
            status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
            message = "RSVP created." if created else "RSVP updated."
            return Response(
                {
                    "status": True,
                    "message": message,
                    "data": {"attendance": response_data},
                },
                status=status_code,
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error in RSVP for event %s", event_id)
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UpdateAttendanceStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        request=UpdateStatusInputSerializer,
        responses={200: EventAttendanceUpdateResponseSerializer},
        examples=[
            OpenApiExample(
                "Update request", value={"status": "maybe"}, request_only=True
            )
        ],
        description="Update attendance status.",
    )
    def patch(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)
            serializer = UpdateStatusInputSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            new_status = serializer.validated_data["status"]
            attendance = EventAttendanceService.update_attendance_status(
                event=event, user=request.user, new_status=new_status
            )
            response_data = EventAttendanceSerializer(
                attendance, context={"request": request}
            ).data
            return Response(
                {
                    "status": True,
                    "message": "Attendance status updated.",
                    "data": {"attendance": response_data},
                }
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error updating attendance status")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserEventsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (optional, defaults to current)",
                required=False,
            ),
            OpenApiParameter(
                name="status",
                type=str,
                description="Filter by RSVP status",
                required=False,
            ),
            OpenApiParameter(
                name="upcoming_only",
                type=bool,
                description="Show only upcoming events",
                required=False,
            ),
            OpenApiParameter(
                name="start_date",
                type=str,
                description="Start date (ISO format)",
                required=False,
            ),
            OpenApiParameter(
                name="end_date",
                type=str,
                description="End date (ISO format)",
                required=False,
            ),
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
        responses={200: UserEventsResponseSerializer},
        description="Get events a user is attending, with optional filters.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id is None:
                user_id = request.query_params.get("user_id")
            if not user_id:
                user = request.user
            else:
                user = get_object_or_404(User, id=user_id)

            status_filter = request.query_params.get("status")
            upcoming_only = (
                request.query_params.get("upcoming_only", "true").lower() == "true"
            )

            start_date_str = request.query_params.get("start_date")
            end_date_str = request.query_params.get("end_date")
            start_date = None
            end_date = None
            if start_date_str:
                try:
                    start_date = timezone.datetime.fromisoformat(
                        start_date_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    return Response(
                        {
                            "status": False,
                            "message": "Invalid start_date format. Use ISO format.",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if end_date_str:
                try:
                    end_date = timezone.datetime.fromisoformat(
                        end_date_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    return Response(
                        {
                            "status": False,
                            "message": "Invalid end_date format. Use ISO format.",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            events = EventAttendanceService.get_user_events(
                user=user,
                status=status_filter,
                upcoming_only=upcoming_only,
                start_date=start_date,
                end_date=end_date,
            )

            accessible_events = []
            for event in events:
                has_access, _ = EventService.check_user_access(event, request.user)
                if has_access or event.event_type == "public":
                    accessible_events.append(event)

            paginator = EventsPagination()
            page = paginator.paginate_queryset(accessible_events, request)
            paginated_data = wrap_paginated_attendance(
                paginator, page, request, EventListSerializer
            )
            return Response(
                {
                    "status": True,
                    "message": "User events retrieved.",
                    "data": paginated_data,
                }
            )
        except Exception as e:
            logger.exception("Error retrieving user events")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserAttendanceStatisticsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                description="User ID (optional, defaults to current)",
                required=False,
            ),
        ],
        responses={200: UserAttendanceStatisticsResponseSerializer},
        examples=[
            OpenApiExample(
                "Statistics response",
                value={
                    "status": True,
                    "message": "Statistics retrieved.",
                    "data": {
                        "statistics": {
                            "total_rsvps": 12,
                            "status_breakdown": {"going": 8, "maybe": 3, "declined": 1},
                            "upcoming_events": 5,
                            "past_events_attended": 7,
                            "events_organized": 2,
                            "attendance_rate": 87.5,
                        }
                    },
                },
                response_only=True,
            )
        ],
        description="Get attendance statistics for a user.",
    )
    def get(self, request, user_id=None):
        try:
            if user_id is None:
                user_id = request.query_params.get("user_id")
            if not user_id:
                user = request.user
                if not user.is_authenticated:
                    return Response(
                        {
                            "status": False,
                            "message": "Authentication required",
                            "data": None,
                        },
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
            else:
                user = get_object_or_404(User, id=user_id)

            if user != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "You can only view your own statistics",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            statistics = EventAttendanceService.get_user_attendance_statistics(user)
            return Response(
                {
                    "status": True,
                    "message": "Statistics retrieved.",
                    "data": {"statistics": statistics},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving attendance statistics")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MutualAttendeesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        responses={200: MutualAttendeesResponseSerializer},
        examples=[
            OpenApiExample(
                "Mutual attendees response",
                value={
                    "status": True,
                    "message": "Mutual attendees retrieved.",
                    "data": {
                        "attendees": [
                            {
                                "user": {"id": 2, "username": "alice", "name": "Alice Smith"},
                                "is_following": True,
                                "is_followed_by": True,
                                "is_mutual": True,
                            }
                        ]
                    },
                },
                response_only=True,
            )
        ],
        description="Get list of attendees that the current user has a follow relationship with.",
    )
    def get(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)
            has_access, message = EventService.check_user_access(event, request.user)
            if not has_access:
                return Response(
                    {
                        "status": False,
                        "message": message,
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            mutual_attendees = EventAttendanceService.get_mutual_attendees(
                event, request.user
            )
            formatted_attendees = [
                {
                    "user": {
                        "id": attendee["user"].id,
                        "username": attendee["user"].username,
                        "name": attendee["user"].get_full_name(),
                    },
                    "is_following": attendee["is_following"],
                    "is_followed_by": attendee["is_followed_by"],
                    "is_mutual": attendee["is_mutual"],
                }
                for attendee in mutual_attendees
            ]
            return Response(
                {
                    "status": True,
                    "message": "Mutual attendees retrieved.",
                    "data": {"attendees": formatted_attendees},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving mutual attendees")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AttendanceTrendView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        parameters=[
            OpenApiParameter(
                name="hours_before",
                type=int,
                description="Hours before event to include",
                required=False,
            ),
        ],
        responses={200: AttendanceTrendResponseSerializer},
        examples=[
            OpenApiExample(
                "Attendance trend example",
                value={
                    "status": True,
                    "message": "Attendance trend retrieved.",
                    "data": {
                        "trend": [
                            {"hour": "2026-03-19T10:00:00Z", "count": 5},
                            {"hour": "2026-03-19T11:00:00Z", "count": 8},
                            {"hour": "2026-03-19T12:00:00Z", "count": 12},
                        ]
                    },
                },
                response_only=True,
            )
        ],
        description="Get RSVP trend (counts per hour) for an event. Only event organizer can access.",
    )
    def get(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)
            if event.organizer != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "Only event organizer can view attendance trend",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            hours_before = int(request.query_params.get("hours_before", 48))
            trend = EventAttendanceService.get_attendance_trend(event, hours_before)
            return Response(
                {
                    "status": True,
                    "message": "Attendance trend retrieved.",
                    "data": {"trend": trend},
                }
            )
        except Exception as e:
            logger.exception("Error retrieving attendance trend")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SendRemindersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Event Attendance"],
        request=SendRemindersInputSerializer,
        responses={200: SendRemindersResponseSerializer},
        examples=[
            OpenApiExample(
                "Reminder response",
                value={
                    "status": True,
                    "message": "Reminders sent.",
                    "data": {
                        "event_id": 1,
                        "hours_before": 24,
                        "reminders_sent": 3,
                        "attendees_to_remind": [
                            {"user_id": 5, "username": "john", "email": "john@example.com"}
                        ],
                    },
                },
                response_only=True,
            )
        ],
        description="Trigger reminders for attendees. Only event organizer can access.",
    )
    @transaction.atomic
    def post(self, request, event_id):
        try:
            event = get_object_or_404(Event, id=event_id)
            if event.organizer != request.user:
                return Response(
                    {
                        "status": False,
                        "message": "Only event organizer can send reminders",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = SendRemindersInputSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Validation error.",
                        "data": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            hours_before = serializer.validated_data["hours_before"]
            reminders = EventAttendanceService.send_reminders(event, hours_before)
            response_data = {
                "event_id": event_id,
                "hours_before": hours_before,
                "reminders_sent": len(reminders),
                "attendees_to_remind": [
                    {
                        "user_id": r["user"].id,
                        "username": r["user"].username,
                        "email": r["email"],
                    }
                    for r in reminders
                ],
            }
            return Response(
                {
                    "status": True,
                    "message": "Reminders sent.",
                    "data": response_data,
                }
            )
        except Exception as e:
            logger.exception("Error sending reminders")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong.",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )