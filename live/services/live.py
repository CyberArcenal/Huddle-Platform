import secrets
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from typing import List, Optional, Dict, Any
from live.models.live import LiveStream, LiveParticipant, LiveJoinRequest
from live.services.livekit import create_livekit_room, delete_livekit_room, get_livekit_token
from users.models import User


class LiveService:
    """Business logic for live streams."""

    @staticmethod
    def generate_stream_key() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    @transaction.atomic
    def start_live(host: User, title: str, description: str = "",
                   allow_requests: bool = True, max_participants: int = 10,
                   is_private: bool = False) -> tuple[LiveStream, str]:
        """Host starts a new live stream."""
        # Check if user already has an active live
        if LiveStream.objects.filter(host=host, status='live').exists():
            raise ValidationError("You already have an active live stream.")

        live:LiveStream = LiveStream.objects.create(
            host=host,
            title=title,
            description=description,
            status='live',
            started_at=timezone.now(),
            allow_requests=allow_requests,
            max_participants=max_participants,
            is_private=is_private,
            stream_key=LiveService.generate_stream_key(),
        )
        # Host automatically becomes a participant
        LiveParticipant.objects.create(live=live, user=host, role='host')
    
        # Create LiveKit room
        room_name = f"live_{live.id}"
        success = create_livekit_room(room_name, max_participants=max_participants)
        if not success:
            raise ValidationError("Failed to create LiveKit room.")

        # Generate token for host
        host_token = get_livekit_token(room_name, identity=f"user_{host.id}", name=host.username)
        
        # Save room name and token (add fields to LiveStream model if needed)
        live.livekit_room = room_name
        live.host_token = host_token  # optional, or return directly
        live.save()
        
        return live, host_token

    @staticmethod
    @transaction.atomic
    def end_live(live: LiveStream, user: User) -> bool:
        """End a live stream (only host)."""
        if live.host != user:
            raise PermissionDenied("Only the host can end this stream.")
        if live.status != 'live':
            raise ValidationError("Stream is not live.")

        live.status = 'ended'
        live.ended_at = timezone.now()
        live.save()

        # Mark all participants as left
        LiveParticipant.objects.filter(live=live, left_at__isnull=True).update(left_at=timezone.now())
        # Reject all pending requests
        LiveJoinRequest.objects.filter(live=live, status='pending').update(status='rejected', responded_at=timezone.now())
        
        # Delete LiveKit room to free resources
        if hasattr(live, 'livekit_room') and live.livekit_room:
            delete_livekit_room(live.livekit_room)
            
        return True

    @staticmethod
    def get_active_streams(exclude_user: Optional[User] = None, limit: int = 20) -> List[LiveStream]:
        """List all currently live streams (public)."""
        qs = LiveStream.objects.filter(status='live', is_private=False)
        if exclude_user:
            qs = qs.exclude(host=exclude_user)
        return list(qs.select_related('host').order_by('-started_at')[:limit])

    @staticmethod
    def get_live_by_id(live_id: int, user: Optional[User] = None) -> Optional[LiveStream]:
        """Retrieve a live stream, checking privacy."""
        try:
            live = LiveStream.objects.get(id=live_id)
        except LiveStream.DoesNotExist:
            return None

        if live.status != 'live':
            return None
        if live.is_private and (not user or (user != live.host and not LiveParticipant.objects.filter(live=live, user=user).exists())):
            return None
        return live

    # ---------- Join requests ----------
    # live/services/live.py - request_join method

    @staticmethod
    def request_join(user: User, live: LiveStream, message: str = "") -> LiveJoinRequest:
        """Viewer requests to join a live stream."""
        if not live.allow_requests:
            raise ValidationError("This host is not accepting join requests.")
        if live.status != 'live':
            raise ValidationError("Stream is not active.")
        if user == live.host:
            raise ValidationError("Host cannot request to join.")
        
        # Check existing request
        existing = LiveJoinRequest.objects.filter(live=live, user=user).first()
        
        if existing:
            if existing.status == 'pending':
                raise ValidationError("You already have a pending request.")
            if existing.status == 'approved':
                raise ValidationError("You are already approved to join.")
            # Kung rejected o canceled, i-update lang sa pending
            if existing.status in ['rejected', 'canceled']:
                with transaction.atomic():
                    existing.status = 'pending'
                    existing.message = message
                    existing.requested_at = timezone.now()  # refresh timestamp
                    existing.responded_at = None
                    existing.save()
                return existing
        
        # Check participant count
        current_participants = LiveParticipant.objects.filter(live=live, left_at__isnull=True).count()
        if current_participants >= live.max_participants:
            raise ValidationError("Live stream is full.")
        
        with transaction.atomic():
            request_obj = LiveJoinRequest.objects.create(
                live=live, user=user, message=message, status='pending'
            )
            return request_obj

    @staticmethod
    def respond_to_request(host: User, request_id: int, approve: bool) -> LiveJoinRequest:
        """Host approves or rejects a join request."""
        try:
            join_req = LiveJoinRequest.objects.select_related('live').get(id=request_id)
        except LiveJoinRequest.DoesNotExist:
            raise ValidationError("Request not found.")

        if join_req.live.host != host:
            raise PermissionDenied("Only the host can respond to requests.")
        if join_req.live.status != 'live':
            raise ValidationError("Stream is no longer live.")
        if join_req.status != 'pending':
            raise ValidationError(f"Request already {join_req.status}.")

        with transaction.atomic():
            if approve:
                # Check participant limit again
                current = LiveParticipant.objects.filter(live=join_req.live, left_at__isnull=True).count()
                if current >= join_req.live.max_participants:
                    raise ValidationError("Stream is full.")
                join_req.status = 'approved'
                # Add as participant (role 'viewer')
                LiveParticipant.objects.create(live=join_req.live, user=join_req.user, role='viewer')
            else:
                join_req.status = 'rejected'
            join_req.responded_at = timezone.now()
            join_req.save()
        return join_req

    @staticmethod
    def cancel_request(user: User, live: LiveStream) -> bool:
        """Cancel a pending request."""
        qs = LiveJoinRequest.objects.filter(live=live, user=user, status='pending')
        if not qs.exists():
            return False
        qs.update(status='canceled', responded_at=timezone.now())
        return True

    @staticmethod
    def get_pending_requests(live: LiveStream, host: User) -> List[LiveJoinRequest]:
        """List all pending join requests for a live (host only)."""
        if live.host != host:
            raise PermissionDenied()
        return list(live.join_requests.filter(status='pending').select_related('user').order_by('requested_at'))

    # ---------- Participants ----------
    @staticmethod
    def get_participants(live: LiveStream, include_left: bool = False) -> List[LiveParticipant]:
        """List participants (host + approved viewers)."""
        qs = live.participants.select_related('user')
        if not include_left:
            qs = qs.filter(left_at__isnull=True)
        return list(qs.order_by('joined_at'))

    @staticmethod
    def leave_live(user: User, live: LiveStream) -> bool:
        """A participant leaves the stream."""
        participant = LiveParticipant.objects.filter(live=live, user=user, left_at__isnull=True).first()
        if not participant:
            return False
        participant.left_at = timezone.now()
        participant.save()
        return True