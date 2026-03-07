from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError

from groups.serializers.base import GroupMinimalSerializer
from users.serializers.user import UserMinimalSerializer

from ..models import Event
from ..services import EventService


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
        # Get the requesting user from context
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        # Add organizer to data
        data["organizer"] = request.user

        # Validate event type and group relationship
        event_type = data.get("event_type", "public")
        group = data.get("group")

        if event_type == "group" and not group:
            raise serializers.ValidationError({"group": "Group events require a group"})

        if event_type != "group" and group:
            raise serializers.ValidationError(
                {"group": "Only group events can be associated with a group"}
            )

        # Validate time
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

        # Validate max attendees
        max_attendees = data.get("max_attendees")
        if max_attendees is not None and max_attendees <= 0:
            raise serializers.ValidationError(
                {"max_attendees": "Max attendees must be positive"}
            )

        return data

    def create(self, validated_data):
        """Create event using EventService"""
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
        # Get the event instance
        event = self.instance

        # Check if event has already started
        if event.start_time <= timezone.now():
            raise serializers.ValidationError(
                "Cannot update event that has already started"
            )

        # Validate time updates
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

        # Validate max attendees
        max_attendees = data.get("max_attendees", event.max_attendees)
        if max_attendees is not None and max_attendees <= 0:
            raise serializers.ValidationError(
                {"max_attendees": "Max attendees must be positive"}
            )

        return data

    def update(self, instance, validated_data):
        """Update event using EventService"""
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

    def get_is_full(self, obj):
        """Check if event is full"""
        return EventService.is_event_full(obj)

    def get_attendees_count(self, obj):
        """Get number of attendees"""
        from ..services import EventAttendanceService

        return EventAttendanceService.get_attendance_count(obj, status="going")

    def get_user_status(self, obj):
        """Get current user's attendance status"""
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

    def get_statistics(self, obj):
        """Get event statistics"""
        try:
            return EventService.get_event_statistics(obj)
        except:
            return {}

    def get_can_edit(self, obj):
        """Check if current user can edit the event"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.organizer == request.user
        return False

    def get_can_delete(self, obj):
        """Check if current user can delete the event"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.organizer == request.user
        return False

    def get_can_rsvp(self, obj):
        """Check if current user can RSVP to the event"""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        # Check access
        has_access, _ = EventService.check_user_access(obj, request.user)
        if not has_access:
            return False

        # Check if event is full
        if EventService.is_event_full(obj):
            return False

        # Check if event hasn't ended
        if obj.end_time < timezone.now():
            return False

        return True


class EventSerializer(serializers.ModelSerializer):
    """Main Event serializer that chooses based on context"""

    def __new__(cls, *args, **kwargs):
        """Return appropriate serializer based on context"""
        context = kwargs.get("context", {})
        request = context.get("request")

        if request:
            if request.method == "POST":
                return EventCreateSerializer(*args, **kwargs)
            elif request.method in ["PUT", "PATCH"]:
                return EventUpdateSerializer(*args, **kwargs)
            elif request.method == "GET":
                # Check if we're listing or retrieving single
                view = context.get("view")
                if view and hasattr(view, "action"):
                    if view.action == "list":
                        return EventListSerializer(*args, **kwargs)
                    elif view.action == "retrieve":
                        return EventDetailSerializer(*args, **kwargs)

        # Default to list serializer
        return EventListSerializer(*args, **kwargs)

    class Meta:
        model = Event
        fields = "__all__"
