from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError

from users.serializers.user import UserMinimalSerializer
from ..models import EventAttendance
from ..services import EventAttendanceService, EventService
from .event import EventListSerializer


class EventAttendanceCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating event attendance (RSVP)"""

    class Meta:
        model = EventAttendance
        fields = ["event", "status"]
        extra_kwargs = {
            "event": {"required": True},
            "status": {"required": True, "default": "going"},
        }

    def validate(self, data):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        event = data.get("event")
        status = data.get("status", "going")

        # Check if user is trying to RSVP as organizer
        if event.organizer == request.user and status != "going":
            raise serializers.ValidationError(
                {"status": "Event organizer must be 'going'"}
            )

        # Check event access
        has_access, message = EventService.check_user_access(event, request.user)
        if not has_access:
            raise serializers.ValidationError({"event": f"Cannot RSVP: {message}"})

        # Check if event is full
        if status == "going" and EventService.is_event_full(event):
            raise serializers.ValidationError({"event": "Event is at full capacity"})

        # Check if event has already ended
        if event.end_time < timezone.now():
            raise serializers.ValidationError({"event": "Cannot RSVP to past event"})

        return data

    def create(self, validated_data):
        """Create attendance using EventAttendanceService"""
        request = self.context.get("request")
        event = validated_data["event"]
        status = validated_data["status"]

        try:
            created, attendance = EventAttendanceService.rsvp_to_event(
                event=event, user=request.user, status=status
            )
            return attendance
        except ValidationError as e:
            raise serializers.ValidationError(e.message_dict)


class EventAttendanceUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating event attendance status"""

    class Meta:
        model = EventAttendance
        fields = ["status"]

    def validate(self, data):
        request = self.context.get("request")
        attendance = self.instance

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        # Check if user owns this attendance record
        if attendance.user != request.user:
            raise serializers.ValidationError("You can only update your own attendance")

        # Check if user is organizer
        if attendance.event.organizer == request.user:
            raise serializers.ValidationError(
                "Event organizer cannot change RSVP status"
            )

        new_status = data.get("status")
        event = attendance.event

        # Check if changing to 'going' when event is full
        if new_status == "going" and attendance.status != "going":
            if EventService.is_event_full(event):
                raise serializers.ValidationError(
                    {"status": "Event is at full capacity"}
                )

        return data

    def update(self, instance, validated_data):
        """Update attendance status using EventAttendanceService"""
        try:
            return EventAttendanceService.update_attendance_status(
                event=instance.event,
                user=instance.user,
                new_status=validated_data["status"],
            )
        except ValidationError as e:
            raise serializers.ValidationError(e.message_dict)


class EventAttendanceSerializer(serializers.ModelSerializer):
    """Serializer for event attendance records"""

    user = UserMinimalSerializer(read_only=True)
    event = EventListSerializer(read_only=True)

    class Meta:
        model = EventAttendance
        fields = ["id", "event", "user", "status", "joined_at"]
        read_only_fields = fields


class EventAttendanceWithUserSerializer(serializers.ModelSerializer):
    """Serializer for attendance with user details (for event attendee list)"""

    user = UserMinimalSerializer(read_only=True)
    is_following = serializers.SerializerMethodField()
    is_followed_by = serializers.SerializerMethodField()

    class Meta:
        model = EventAttendance
        fields = ["id", "user", "status", "joined_at", "is_following", "is_followed_by"]
        read_only_fields = fields

    def get_is_following(self, obj):
        """Check if current user is following this attendee"""
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user != obj.user:
            # Assuming you have a UserFollowService
            try:
                from users.services import UserFollowService

                return UserFollowService.is_following(request.user, obj.user)
            except ImportError:
                return False
        return False

    def get_is_followed_by(self, obj):
        """Check if this attendee is following current user"""
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user != obj.user:
            try:
                from users.services import UserFollowService

                return UserFollowService.is_following(obj.user, request.user)
            except ImportError:
                return False
        return False


class EventStatisticsSerializer(serializers.Serializer):
    """Serializer for event statistics"""

    total_attendees = serializers.IntegerField()
    going_count = serializers.IntegerField()
    maybe_count = serializers.IntegerField()
    declined_count = serializers.IntegerField()
    is_full = serializers.BooleanField()
    remaining_spots = serializers.IntegerField(allow_null=True)
    days_until_event = serializers.IntegerField()
    duration_hours = serializers.FloatField()
    organizer = serializers.DictField()
    group = serializers.CharField(allow_null=True)

    class Meta:
        fields = [
            "total_attendees",
            "going_count",
            "maybe_count",
            "declined_count",
            "is_full",
            "remaining_spots",
            "days_until_event",
            "duration_hours",
            "organizer",
            "group",
        ]


class EventTimelineSerializer(serializers.Serializer):
    """Serializer for event timeline"""

    event = EventListSerializer()
    type = serializers.CharField()  # 'organized' or 'attending'
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    duration = serializers.DurationField()

    class Meta:
        fields = ["event", "type", "start_time", "end_time", "duration"]


class UserAttendanceStatisticsSerializer(serializers.Serializer):
    """Serializer for user's event attendance statistics"""

    total_rsvps = serializers.IntegerField()
    status_breakdown = serializers.DictField()
    upcoming_events = serializers.IntegerField()
    past_events_attended = serializers.IntegerField()
    events_organized = serializers.IntegerField()
    attendance_rate = serializers.FloatField()

    class Meta:
        fields = [
            "total_rsvps",
            "status_breakdown",
            "upcoming_events",
            "past_events_attended",
            "events_organized",
            "attendance_rate",
        ]
