"""Broadcasts real-time assist prompts to connected agent-ui clients.

Simple broadcast-to-all rather than per-call rooms: at pilot scale (2-3
seats) every agent-ui instance filters client-side by its own call_id, which
is far less machinery than a proper pub/sub room system. Revisit if this
needs to scale to real seat counts.
"""
import asyncio
import json
import logging

import websockets
from websockets.server import WebSocketServerProtocol

log = logging.getLogger("ws_server")


class Broadcaster:
    def __init__(self):
        self._clients: set[WebSocketServerProtocol] = set()

    async def register(self, ws: WebSocketServerProtocol) -> None:
        self._clients.add(ws)
        log.info("agent-ui client connected (%d total)", len(self._clients))

    async def unregister(self, ws: WebSocketServerProtocol) -> None:
        self._clients.discard(ws)
        log.info("agent-ui client disconnected (%d total)", len(self._clients))

    async def broadcast(self, message: dict) -> None:
        if not self._clients:
            return
        payload = json.dumps(message)
        await asyncio.gather(
            *(client.send(payload) for client in list(self._clients)),
            return_exceptions=True,
        )


async def run_ws_server(broadcaster: Broadcaster, port: int):
    async def handler(ws: WebSocketServerProtocol):
        await broadcaster.register(ws)
        try:
            async for _ in ws:
                pass  # agent-ui doesn't send messages, just listens
        finally:
            await broadcaster.unregister(ws)

    log.info("realtime-assist websocket server listening on 0.0.0.0:%s", port)
    async with websockets.serve(handler, "0.0.0.0", port):
        await asyncio.Future()  # run forever
