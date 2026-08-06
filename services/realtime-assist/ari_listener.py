"""
Real-time assist entrypoint.

Connects to Asterisk's ARI websocket as the 'assist_app' Stasis application.
For every call that enters Stasis (see asterisk/conf/extensions.conf):

  1. Record it in the `calls` table.
  2. Attach a Snoop channel (spy=both) to it so we can listen without being
     in the actual call's audio path.
  3. Create an ARI External Media channel pointed at a per-call UDP port on
     this container, and bridge the Snoop + External Media channels together
     — this is what streams live RTP audio to us.
  4. Hand the original channel back to the dialplan (`continue`) so the real
     Dial()/Playback() proceeds completely unaffected by any of the above.

Each per-call audio tap (chunker.CallAudioTap) buffers ~12s of audio, then
fires a callback that transcribes the chunk, decides whether the agent needs
a nudge, writes both to Postgres, and — if there's a nudge — broadcasts it to
agent-ui over ws_server.

This is the standard ARI Snoop + External Media pattern used for building
real-time voice AI listeners on Asterisk. It has been written to the
documented ARI contract but not exercised against a live Asterisk instance
in this environment — verify the exact request shapes against your
Asterisk version's ARI docs (`/ari/api-docs`) before relying on it in
production. See README "What's been verified vs. what needs a live check."
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass

import aiohttp

import db
import prompt_engine
from chunker import CallAudioTap
from ws_server import Broadcaster, run_ws_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s realtime-assist %(message)s")
log = logging.getLogger("ari_listener")

ARI_URL = os.environ.get("ARI_URL", "http://asterisk:8088/ari")
ARI_USER = os.environ.get("ARI_USER", "asterisk")
ARI_PASSWORD = os.environ.get("ARI_PASSWORD", "changeme_ari_password")
ARI_APP = os.environ.get("ARI_APP", "assist_app")
WS_PORT = int(os.environ.get("WS_PORT", "8765"))

# Hostname the Asterisk container resolves us at (Docker Compose service DNS).
SELF_HOST = os.environ.get("SELF_HOST", "realtime-assist")
PORT_POOL_START = 5050
PORT_POOL_SIZE = 30


@dataclass
class CallState:
    primary_channel_id: str
    snoop_id: str
    extmedia_id: str
    bridge_id: str
    port: int
    tap: CallAudioTap


class AriListener:
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._auth = aiohttp.BasicAuth(ARI_USER, ARI_PASSWORD)
        self._active_calls: dict[str, CallState] = {}
        self._channel_to_call: dict[str, str] = {}
        self._free_ports = list(range(PORT_POOL_START, PORT_POOL_START + PORT_POOL_SIZE))
        self._broadcaster = Broadcaster()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def _rest(self, method: str, path: str, **params) -> dict:
        url = f"{ARI_URL}{path}"
        async with self._session.request(method, url, params=params, auth=self._auth) as resp:
            resp.raise_for_status()
            if resp.content_type == "application/json":
                return await resp.json()
            return {}

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._session = aiohttp.ClientSession()
        ws_url = ARI_URL.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/events?app={ARI_APP}&api_key={ARI_USER}:{ARI_PASSWORD}&subscribeAll=true"

        await asyncio.gather(
            run_ws_server(self._broadcaster, WS_PORT),
            self._event_loop(ws_url),
        )

    async def _event_loop(self, ws_url: str) -> None:
        """Reconnects with backoff on any disconnect (Asterisk restart, network
        blip, etc.) — confirmed live that without this, a dropped websocket
        just goes silent forever: the process keeps running (ws_server is a
        separate task in the same gather()) but stops processing any calls,
        with no crash and no error logged. That's worse than crashing."""
        backoff = 1
        while True:
            try:
                log.info("connecting to ARI websocket at %s", ws_url)
                async with self._session.ws_connect(ws_url) as ws:
                    log.info("connected, listening for calls in app '%s'", ARI_APP)
                    backoff = 1
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            event = json.loads(msg.data)
                            await self._handle_event(event)
                        except Exception:
                            log.exception("failed to handle ARI event: %s", msg.data)
                log.warning("ARI websocket closed, reconnecting in %ss", backoff)
            except Exception:
                log.exception("ARI websocket connection failed, retrying in %ss", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _handle_event(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "StasisStart":
            await self._on_stasis_start(event)
        elif etype == "ChannelDestroyed":
            # Confirmed live: StasisEnd fires the instant we call `continue`
            # to hand the channel back to the dialplan — milliseconds into
            # the call, not at hangup. Using it for cleanup was tearing down
            # the Snoop/External Media bridge and marking the call "ended"
            # before Playback/Dial even started, so the realtime-assist tap
            # never captured anything. ChannelDestroyed fires at the actual
            # hangup, once MixMonitor has finished writing the recording.
            await self._on_channel_destroyed(event)

    async def _on_stasis_start(self, event: dict) -> None:
        channel = event["channel"]
        channel_id = channel["id"]
        args = event.get("args", [])

        # Skip our own snoop/external-media helper channels re-entering Stasis.
        if channel_id in {s.snoop_id for s in self._active_calls.values()} or \
           channel_id in {s.extmedia_id for s in self._active_calls.values()}:
            return

        call_type = args[0] if len(args) > 0 else "unknown"
        call_id = args[1] if len(args) > 1 else channel_id
        agent_ext = channel.get("caller", {}).get("number")

        log.info("call started: call_id=%s type=%s channel=%s", call_id, call_type, channel_id)
        await self._db_call(db.upsert_call_started, call_id, call_type, agent_ext)

        if not self._free_ports:
            log.error("no free UDP ports for audio tap, call %s will not get realtime assist", call_id)
            await self._rest("POST", f"/channels/{channel_id}/continue")
            return
        port = self._free_ports.pop()

        try:
            snoop = await self._rest(
                "POST", f"/channels/{channel_id}/snoop",
                spy="both", app=ARI_APP, snoopId=f"snoop-{call_id}",
            )
            extmedia = await self._rest(
                "POST", "/channels/externalMedia",
                app=ARI_APP, external_host=f"{SELF_HOST}:{port}",
                format="ulaw", transport="udp", channelId=f"extmedia-{call_id}",
            )
            bridge = await self._rest("POST", "/bridges", type="mixing", bridgeId=f"bridge-{call_id}")
            await self._rest(
                "POST", f"/bridges/{bridge['id']}/addChannel",
                channel=f"{snoop['id']},{extmedia['id']}",
            )

            tap = CallAudioTap(call_id, port, self._on_chunk_ready)
            await tap.start()

            self._active_calls[call_id] = CallState(
                primary_channel_id=channel_id,
                snoop_id=snoop["id"],
                extmedia_id=extmedia["id"],
                bridge_id=bridge["id"],
                port=port,
                tap=tap,
            )
            self._channel_to_call[channel_id] = call_id
        except Exception:
            log.exception("failed to set up audio tap for call %s — continuing call without realtime assist", call_id)
            self._free_ports.append(port)

        # Hand control back to the dialplan so Dial()/Playback() proceeds.
        await self._rest("POST", f"/channels/{channel_id}/continue")

    async def _on_channel_destroyed(self, event: dict) -> None:
        channel_id = event["channel"]["id"]
        call_id = self._channel_to_call.pop(channel_id, None)
        if not call_id:
            return  # a snoop/extmedia helper channel ending, nothing to do

        state = self._active_calls.pop(call_id, None)
        if state:
            await state.tap.stop()
            self._free_ports.append(state.port)
            for cleanup_path in (
                f"/bridges/{state.bridge_id}",
                f"/channels/{state.snoop_id}",
                f"/channels/{state.extmedia_id}",
            ):
                try:
                    await self._rest("DELETE", cleanup_path)
                except Exception:
                    pass  # Asterisk usually tears these down on its own already

        log.info("call ended: call_id=%s", call_id)
        await self._db_call(db.mark_call_ended, call_id)

    async def _on_chunk_ready(self, call_id: str, chunk_index: int, wav_bytes: bytes) -> None:
        transcript = await self._loop.run_in_executor(
            None, prompt_engine.transcribe_chunk, wav_bytes
        )
        if not transcript:
            return
        await self._db_call(db.insert_transcript_chunk, call_id, chunk_index, transcript)

        suggestion = await self._loop.run_in_executor(
            None, prompt_engine.maybe_generate_nudge, transcript
        )
        if not suggestion:
            return

        await self._db_call(db.insert_realtime_prompt, call_id, chunk_index, suggestion)
        await self._broadcaster.broadcast({
            "call_id": call_id,
            "chunk_index": chunk_index,
            "prompt_text": suggestion,
        })
        log.info("nudge for call %s chunk %s: %s", call_id, chunk_index, suggestion)

    async def _db_call(self, fn, *args) -> None:
        """Runs a blocking psycopg2 call (own short-lived connection) off
        the event loop thread. A fresh connection per call is wasteful at
        real scale but simplest and safest at pilot call volumes."""
        def _run():
            conn = db.connect()
            try:
                fn(conn, *args)
            finally:
                conn.close()
        await self._loop.run_in_executor(None, _run)


def main() -> None:
    listener = AriListener()
    asyncio.run(listener.run())


if __name__ == "__main__":
    main()
