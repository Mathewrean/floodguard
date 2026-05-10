from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
from django.urls import re_path
from core import consumers

websocket_urlpatterns = [
    re_path(r'^ws/flood-map/$', consumers.FloodMapConsumer.as_asgi()),
    re_path(r'^ws/alerts/$', consumers.AlertConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})
