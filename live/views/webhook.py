# live/views/webhook.py
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from live.services.live import LiveService
import json

@csrf_exempt
def livekit_webhook(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            event = data.get('event')
            if event == 'room_finished':
                room_name = data.get('room', {}).get('name')
                if room_name and room_name.startswith('live_'):
                    live_id = int(room_name.split('_')[1])
                    # End the stream programmatically
                    from live.models.live import LiveStream
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    try:
                        live = LiveStream.objects.get(id=live_id, status='live')
                        # We need a user to call end_live, but host can be live.host
                        LiveService.end_live(live, live.host)
                    except LiveStream.DoesNotExist:
                        pass
            return HttpResponse(status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return HttpResponse(status=405)