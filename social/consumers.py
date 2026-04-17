import json
import os

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from redis import Redis

from .models import ChatGroup, ChatGroupMember, Friendship, GroupMessage, Message, UserProfile


def _direct_room_name(user_a_id, user_b_id):
    low = min(user_a_id, user_b_id)
    high = max(user_a_id, user_b_id)
    return f"direct_{low}_{high}"


class DirectChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return

        self.peer_username = self.scope["url_route"]["kwargs"]["username"]
        self.peer = await self._get_user(self.peer_username)
        if self.peer is None:
            await self.close()
            return

        if not await self._can_message(user.id, self.peer.id):
            await self.close()
            return

        self.room_group_name = _direct_room_name(user.id, self.peer.id)
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        payload = json.loads(text_data)
        event_type = payload.get("type")
        user = self.scope["user"]

        if event_type == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat.typing",
                    "username": user.username,
                    "is_typing": bool(payload.get("is_typing")),
                },
            )
            return

        if event_type == "read":
            message_id = payload.get("message_id")
            if not message_id:
                return

            updated = await self._mark_message_read(message_id, self.scope["user"].id)
            if updated:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat.receipt",
                        "message_id": message_id,
                        "reader": self.scope["user"].username,
                    },
                )
            return

        if event_type != "message":
            return

        body = (payload.get("body") or "").strip()
        if not body:
            return

        msg = await self._create_direct_message(user.id, self.peer.id, body)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.message",
                "message": {
                    "id": msg["id"],
                    "sender_id": user.id,
                    "sender": user.username,
                    "body": body,
                    "created_at": msg["created_at"],
                },
            },
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({"type": "message", "message": event["message"]}))

    async def chat_typing(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "typing",
                    "username": event["username"],
                    "is_typing": event["is_typing"],
                }
            )
        )

    async def chat_receipt(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "receipt",
                    "message_id": event["message_id"],
                    "reader": event["reader"],
                }
            )
        )

    @database_sync_to_async
    def _get_user(self, username):
        return User.objects.filter(username=username).first()

    @database_sync_to_async
    def _can_message(self, user_id, peer_id):
        return Friendship.objects.filter(
            status=Friendship.STATUS_ACCEPTED,
        ).filter(
            (Q(from_user_id=user_id, to_user_id=peer_id))
            | (Q(from_user_id=peer_id, to_user_id=user_id))
        ).exists()

    @database_sync_to_async
    def _create_direct_message(self, sender_id, recipient_id, body):
        msg = Message.objects.create(sender_id=sender_id, recipient_id=recipient_id, body=body)
        return {
            "id": msg.id,
            "created_at": timezone.localtime(msg.created_at).strftime("%b %d, %H:%M"),
        }

    @database_sync_to_async
    def _mark_message_read(self, message_id, reader_id):
        msg = Message.objects.filter(id=message_id).first()
        if msg is None:
            return False
        if msg.recipient_id != reader_id:
            return False
        if msg.is_read:
            return True
        msg.is_read = True
        msg.read_at = timezone.now()
        msg.save(update_fields=["is_read", "read_at"])
        return True


class GroupChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return

        self.group_id = int(self.scope["url_route"]["kwargs"]["group_id"])
        if not await self._is_member(self.group_id, user.id):
            await self.close()
            return

        self.room_group_name = f"group_{self.group_id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        payload = json.loads(text_data)
        if payload.get("type") != "message":
            return

        body = (payload.get("body") or "").strip()
        if not body:
            return

        user = self.scope["user"]
        msg = await self._create_group_message(self.group_id, user.id, body)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.message",
                "message": {
                    "id": msg["id"],
                    "sender_id": user.id,
                    "sender": user.username,
                    "body": body,
                    "created_at": msg["created_at"],
                },
            },
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({"type": "message", "message": event["message"]}))

    @database_sync_to_async
    def _is_member(self, group_id, user_id):
        return ChatGroupMember.objects.filter(group_id=group_id, user_id=user_id).exists()

    @database_sync_to_async
    def _create_group_message(self, group_id, sender_id, body):
        msg = GroupMessage.objects.create(group_id=group_id, sender_id=sender_id, body=body)
        return {
            "id": msg.id,
            "created_at": timezone.localtime(msg.created_at).strftime("%b %d, %H:%M"),
        }


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return

        self.user_group = f"user_{user.id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def notify_event(self, event):
        await self.send(text_data=json.dumps({"type": "notification", "payload": event["payload"]}))


class PresenceConsumer(AsyncWebsocketConsumer):
    ONLINE_CONNECTIONS = {}
    ONLINE_SET_KEY = "presence:online_users"

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return

        self.username = user.username
        self.user_id = user.id
        self.connection_key = f"presence:conn:{self.channel_name}"
        self.group_name = "presence_global"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self._touch_last_seen(self.user_id)
        await self._mark_online(self.username)
        await self.accept()

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "presence.event",
                "username": self.username,
                "status": "online",
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if hasattr(self, "username"):
            await self._mark_offline(self.username)
            has_connections = await self._user_has_active_connections(self.username)
            if not has_connections:
                await self._touch_last_seen(self.user_id)
                last_seen_text = await self._get_last_seen_text(self.user_id)
                await self.channel_layer.group_send(
                    "presence_global",
                    {
                        "type": "presence.event",
                        "username": self.username,
                        "status": "offline",
                        "last_seen": last_seen_text,
                    },
                )
            else:
                await self.channel_layer.group_send(
                    "presence_global",
                    {
                        "type": "presence.event",
                        "username": self.username,
                        "status": "online",
                    },
                )

    async def receive(self, text_data):
        payload = json.loads(text_data)
        if payload.get("type") == "snapshot":
            users = await self._snapshot_users()
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "presence_snapshot",
                        "users": users,
                    }
                )
            )
        elif payload.get("type") == "heartbeat":
            await self._touch_last_seen(self.user_id)
            await self._refresh_online()

    async def presence_event(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "presence",
                    "username": event["username"],
                    "status": event["status"],
                    "last_seen": event.get("last_seen", ""),
                }
            )
        )

    @database_sync_to_async
    def _touch_last_seen(self, user_id):
        UserProfile.objects.filter(user_id=user_id).update(last_seen=timezone.now())

    @database_sync_to_async
    def _get_last_seen_text(self, user_id):
        profile = UserProfile.objects.filter(user_id=user_id).first()
        if profile is None or profile.last_seen is None:
            return ""
        return timezone.localtime(profile.last_seen).strftime("%b %d, %H:%M")

    @database_sync_to_async
    def _mark_online(self, username):
        PresenceConsumer._local_online(username)
        client = self._redis_client()
        if client is None:
            return
        client.sadd(self.ONLINE_SET_KEY, self.connection_key)
        client.setex(self.connection_key, 90, username)

    @database_sync_to_async
    def _refresh_online(self):
        client = self._redis_client()
        if client is None:
            return
        client.sadd(self.ONLINE_SET_KEY, self.connection_key)
        client.setex(self.connection_key, 90, self.username)

    @database_sync_to_async
    def _mark_offline(self, username):
        PresenceConsumer._local_offline(username)
        client = self._redis_client()
        if client is None:
            return
        client.delete(self.connection_key)
        client.srem(self.ONLINE_SET_KEY, self.connection_key)

    @database_sync_to_async
    def _snapshot_users(self):
        client = self._redis_client()
        if client is None:
            return sorted(PresenceConsumer.ONLINE_CONNECTIONS.keys())

        members = []
        usernames = set()
        stale = []
        for raw in client.smembers(self.ONLINE_SET_KEY):
            conn_key = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            username = client.get(conn_key)
            if username:
                name = username.decode("utf-8") if isinstance(username, bytes) else str(username)
                usernames.add(name)
            else:
                stale.append(conn_key)

        if stale:
            client.srem(self.ONLINE_SET_KEY, *stale)
        return sorted(usernames)

    @database_sync_to_async
    def _user_has_active_connections(self, username):
        if PresenceConsumer.ONLINE_CONNECTIONS.get(username, 0) > 0:
            return True

        client = self._redis_client()
        if client is None:
            return False
        for raw in client.smembers(self.ONLINE_SET_KEY):
            conn_key = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            value = client.get(conn_key)
            if value:
                name = value.decode("utf-8") if isinstance(value, bytes) else str(value)
                if name == username:
                    return True
        return False

    @staticmethod
    def _redis_client():
        redis_url = os.environ.get("REDIS_URL", "")
        if not redis_url:
            return None
        return Redis.from_url(redis_url)

    @staticmethod
    def _local_online(username):
        PresenceConsumer.ONLINE_CONNECTIONS[username] = PresenceConsumer.ONLINE_CONNECTIONS.get(username, 0) + 1

    @staticmethod
    def _local_offline(username):
        if username in PresenceConsumer.ONLINE_CONNECTIONS:
            PresenceConsumer.ONLINE_CONNECTIONS[username] -= 1
            if PresenceConsumer.ONLINE_CONNECTIONS[username] <= 0:
                PresenceConsumer.ONLINE_CONNECTIONS.pop(username, None)


class CallSignalingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return

        self.username = user.username
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.group_name = f"call_{self.room_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "call.signal",
                "sender": self.username,
                "payload": {"type": "join"},
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "call.signal",
                    "sender": self.username,
                    "payload": {"type": "leave"},
                },
            )
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        payload = json.loads(text_data)
        signal_type = payload.get("type")
        if signal_type not in {"offer", "answer", "ice", "hangup", "join"}:
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "call.signal",
                "sender": self.username,
                "payload": payload,
            },
        )

    async def call_signal(self, event):
        payload = event["payload"]
        target = payload.get("target")
        if target and target != self.username:
            return
        await self.send(
            text_data=json.dumps(
                {
                    "type": "call",
                    "sender": event["sender"],
                    "payload": payload,
                }
            )
        )
