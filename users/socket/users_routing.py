
from django.urls import re_path

from users.socket.consumers.online import OnlineStatusConsumer
websocket_urlpatterns = [
    re_path(r'ws/online/$', OnlineStatusConsumer.as_asgi()),
]