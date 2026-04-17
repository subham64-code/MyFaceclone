import json

from django.conf import settings

from .models import Notification


def global_ui_context(request):
    ice_servers_json = json.dumps(getattr(settings, "WEBRTC_ICE_SERVERS", [{"urls": "stun:stun.l.google.com:19302"}]))

    if not request.user.is_authenticated:
        return {
            "unread_notifications": 0,
            "webrtc_ice_servers_json": ice_servers_json,
        }

    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return {
        "unread_notifications": unread_count,
        "webrtc_ice_servers_json": ice_servers_json,
    }
