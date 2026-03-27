from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import Optional, Dict, Any
from groups.serializers.group import GroupMinimalSerializer
from users.serializers.user.profile import UserMinimalSerializer
from ..models import Event
from ..services import EventService


# ----------------------------------------------------------------------
# New serializer for event statistics (matches PostStatisticsSerializer pattern)
# ----------------------------------------------------------------------
class EventStatisticsSerializerData(serializers.Serializer):
    """Statistics for an event."""
    total_attendees = serializers.IntegerField()
    going_count = serializers.IntegerField()
    maybe_count = serializers.IntegerField()
    declined_count = serializers.IntegerField()
    is_full = serializers.BooleanField()
    remaining_spots = serializers.IntegerField(allow_null=True)
    days_until_event = serializers.IntegerField()
    duration_hours = serializers.FloatField()
    organizer = serializers.DictField()  # or you could use a nested UserMinimalSerializer
    group = serializers.CharField(allow_null=True)


# ----------------------------------------------------------------------
# Event serializers
# ----------------------------------------------------------------------
class EventCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating events"""

    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "location",
            "start_time",
            "end_time",
            "event_type",
            "group",
            "max_attendees",
        ]
        extra_kwargs = {
            "group": {"required": False, "allow_null": True},
            "max_attendees": {"required": False, "allow_null": True},
        }

    def validate(self, data):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        data["organizer"] = request.user

        event_type = data.get("event_type", "public")
        group = data.get("group")

        if event_type == "group" and not group:
            raise serializers.ValidationError({"group": "Group events require a group"})
        if event_type != "group" and group:
            raise serializers.ValidationError(
                {"group": "Only group events can be associated with a group"}
            )

        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if start_time and end_time:
            if start_time >= end_time:
                raise serializers.ValidationError(
                    {"end_time": "End time must be after start time"}
                )
            if start_time < timezone.now():
                raise serializers.ValidationError(
                    {"start_time": "Start time cannot be in the past"}
                )

        max_attendees = data.get("max_attendees")
        if max_attendees is not None and max_attendees <= 0:
            raise serializers.ValidationError(
                {"max_attendees": "Max attendees must be positive"}
            )

        return data

    def create(self, validated_data):
        try:
            return EventService.create_event(**validated_data)
        except ValidationError as e:
            raise serializers.ValidationError(e.message_dict)


class EventUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating events"""

    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "location",
            "start_time",
            "end_time",
            "max_attendees",
        ]
        extra_kwargs = {
            "start_time": {"required": False},
            "end_time": {"required": False},
            "max_attendees": {"required": False, "allow_null": True},
        }

    def validate(self, data):
        event = self.instance

        if event.start_time <= timezone.now():
            raise serializers.ValidationError(
                "Cannot update event that has already started"
            )

        start_time = data.get("start_time", event.start_time)
        end_time = data.get("end_time", event.end_time)

        if start_time >= end_time:
            raise serializers.ValidationError(
                {"end_time": "End time must be after start time"}
            )
        if start_time < timezone.now():
            raise serializers.ValidationError(
                {"start_time": "Start time cannot be in the past"}
            )

        max_attendees = data.get("max_attendees", event.max_attendees)
        if max_attendees is not None and max_attendees <= 0:
            raise serializers.ValidationError(
                {"max_attendees": "Max attendees must be positive"}
            )

        return data

    def update(self, instance, validated_data):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        try:
            return EventService.update_event(
                event=instance, update_data=validated_data, updater=request.user
            )
        except ValidationError as e:
            raise serializers.ValidationError(e.message_dict)


class EventListSerializer(serializers.ModelSerializer):
    """Serializer for listing events"""

    organizer = UserMinimalSerializer(read_only=True)
    group = GroupMinimalSerializer(read_only=True)
    is_full = serializers.SerializerMethodField()
    attendees_count = serializers.SerializerMethodField()
    user_status = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "organizer",
            "group",
            "event_type",
            "location",
            "start_time",
            "end_time",
            "max_attendees",
            "created_at",
            "is_full",
            "attendees_count",
            "user_status",
        ]
        read_only_fields = fields

    def get_is_full(self, obj) -> bool:
        return EventService.is_event_full(obj)

    def get_attendees_count(self, obj) -> int:
        from ..services import EventAttendanceService
        return EventAttendanceService.get_attendance_count(obj, status="going")

    def get_user_status(self, obj) -> Optional[str]:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            from ..services import EventAttendanceService
            attendance = EventAttendanceService.get_attendance(obj, request.user)
            return attendance.status if attendance else None
        return None


class EventDetailSerializer(EventListSerializer):
    """Serializer for event details"""

    statistics = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_rsvp = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = EventListSerializer.Meta.fields + [
            "statistics",
            "can_edit",
            "can_delete",
            "can_rsvp",
        ]

    def get_statistics(self, obj) -> EventStatisticsSerializerData:  # type: ignore
        """Return statistics using the dedicated serializer."""
        try:
            stats_data = EventService.get_event_statistics(obj)
            # Return serialized data (dict) – the type hint tells OpenAPI what structure to expect
            return EventStatisticsSerializerData(stats_data, context=self.context).data
        except:
            return {}

    def get_can_edit(self, obj) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.organizer == request.user
        return False

    def get_can_delete(self, obj) -> bool:
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.organizer == request.user
        return False

    def get_can_rsvp(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        has_access, _ = EventService.check_user_access(obj, request.user)
        if not has_access:
            return False

        if EventService.is_event_full(obj):
            return False

        if obj.end_time < timezone.now():
            return False

        return True


class EventSerializer(serializers.ModelSerializer):
    """Main Event serializer that chooses based on context"""

    def __new__(cls, *args, **kwargs):
        context = kwargs.get("context", {})
        request = context.get("request")

        if request:
            if request.method == "POST":
                return EventCreateSerializer(*args, **kwargs)
            elif request.method in ["PUT", "PATCH"]:
                return EventUpdateSerializer(*args, **kwargs)
            elif request.method == "GET":
                view = context.get("view")
                if view and hasattr(view, "action"):
                    if view.action == "list":
                        return EventListSerializer(*args, **kwargs)
                    elif view.action == "retrieve":
                        return EventDetailSerializer(*args, **kwargs)

        return EventListSerializer(*args, **kwargs)

    class Meta:
        model = Event
        fields = "__all__"