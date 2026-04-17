from django.urls import re_path

from live.consumers.live import LiveConsumer

live_websocket_urlpatterns = [
    re_path(r'ws/live/(?P<live_id>\d+)/$', LiveConsumer.as_asgi()),
]