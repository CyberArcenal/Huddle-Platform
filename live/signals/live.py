from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from live.models.live import LiveJoinRequest, LiveStream

@receiver(post_save, sender=LiveJoinRequest)
def broadcast_new_request(sender, instance, created, **kwargs):
    """Kapag may bagong join request (pending), ipaalam sa host."""
    if created and instance.status == 'pending':
        channel_layer = get_channel_layer()
        group_name = f'live_{instance.live_id}'
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'new_request',
                'request': {
                    'id': instance.id,
                    'user_id': instance.user_id,
                    'username': instance.user.username,
                    'message': instance.message,
                    'requested_at': instance.requested_at.isoformat(),
                }
            }
        )
        
@receiver(post_save, sender=LiveJoinRequest)
def broadcast_request_response(sender, instance, created, **kwargs):
    if not created and instance.status != 'pending':
        channel_layer = get_channel_layer()
        group_name = f'live_{instance.live_id}'
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'request_responded',
                'status': instance.status,
                'request_id': instance.id,
            }
        )
        # If approved, also send participant join event
        if instance.status == 'approved':
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'participant_update',
                    'action': 'join',
                    'user_id': instance.user_id,
                    'username': instance.user.username,
                }
            )


@receiver(post_save, sender=LiveStream)
def broadcast_stream_ended(sender, instance, **kwargs):
    if instance.status == 'ended' and not kwargs.get('created', False):
        channel_layer = get_channel_layer()
        group_name = f'live_{instance.id}'
        async_to_sync(channel_layer.group_send)(
            group_name,
            {'type': 'stream_ended'}
        )