import asyncio
from collections import defaultdict

from fastapi import WebSocket

from .models import Role, User


class RealtimeHub:
    """Pilot-safe in-process event routing.

    One API worker is intentional for the 1-3 seat pilot. A Redis-backed fanout
    replaces this implementation before horizontal API scaling.
    """

    def __init__(self) -> None:
        self._by_user: dict[str, set[WebSocket]] = defaultdict(set)
        self._users: dict[str, User] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user: User, websocket: WebSocket) -> None:
        async with self._lock:
            self._users[user.id] = user
            self._by_user[user.id].add(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._by_user.get(user_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._by_user.pop(user_id, None)
                self._users.pop(user_id, None)

    async def publish(self, tenant_id: str, event: dict, assigned_user_id: str | None = None) -> None:
        recipients: list[WebSocket] = []
        async with self._lock:
            for user_id, connections in self._by_user.items():
                user = self._users[user_id]
                if user.tenant_id != tenant_id:
                    continue
                can_supervise = user.role in {Role.ADMIN, Role.SUPERVISOR, Role.QA_REVIEWER}
                is_assignee = assigned_user_id is not None and user.id == assigned_user_id
                if can_supervise or is_assignee:
                    recipients.extend(connections)
        if recipients:
            await asyncio.gather(*(ws.send_json(event) for ws in recipients), return_exceptions=True)


realtime_hub = RealtimeHub()

