"""
Per-call audio chunker.

Asterisk's ARI External Media feature streams a channel's audio to us as
RTP/u-law over UDP once we bridge a Snoop channel into it (see
ari_listener.py). Each active call gets its own dedicated UDP port so
incoming packets can be attributed to the right call_id — Asterisk's
external_host only gives us a destination address, not per-packet call
identity, so port-per-call is the simplest correct way to demux multiple
concurrent calls.

This module owns: binding that per-call UDP socket, stripping the (minimal,
no-extension) 12-byte RTP header, decoding u-law -> 16-bit PCM, and firing a
callback with a WAV blob once ~CHUNK_SECONDS of audio has accumulated.
"""
import asyncio
import audioop
import io
import logging
import wave
from dataclasses import dataclass, field
from typing import Callable, Awaitable

log = logging.getLogger("chunker")

SAMPLE_RATE = 8000  # standard for ulaw/alaw telephony audio
RTP_HEADER_LEN = 12
CHUNK_SECONDS = 12  # within the agreed 10-15s near-real-time window

ChunkCallback = Callable[[str, int, bytes], Awaitable[None]]


@dataclass
class _CallBuffer:
    pcm_bytes: bytearray = field(default_factory=bytearray)
    chunk_index: int = 0


class CallAudioTap:
    """One instance per active call. Binds a UDP socket, decodes RTP/ulaw,
    and calls `on_chunk_ready(call_id, wav_bytes)` every CHUNK_SECONDS."""

    def __init__(self, call_id: str, udp_port: int, on_chunk_ready: ChunkCallback):
        self.call_id = call_id
        self.udp_port = udp_port
        self.on_chunk_ready = on_chunk_ready
        self._buf = _CallBuffer()
        self._transport: asyncio.DatagramTransport | None = None
        self._flush_task: asyncio.Task | None = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _RtpProtocol(self._on_packet),
            local_addr=("0.0.0.0", self.udp_port),
        )
        self._flush_task = asyncio.create_task(self._flush_loop())
        log.info("audio tap for call %s listening on udp/%s", self.call_id, self.udp_port)

    def _on_packet(self, data: bytes) -> None:
        if len(data) <= RTP_HEADER_LEN:
            return
        ulaw_payload = data[RTP_HEADER_LEN:]
        try:
            pcm = audioop.ulaw2lin(ulaw_payload, 2)
        except audioop.error:
            return
        self._buf.pcm_bytes.extend(pcm)

    async def _flush_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(CHUNK_SECONDS)
                await self._flush()
        except asyncio.CancelledError:
            await self._flush()  # flush whatever's left on shutdown
            raise

    async def _flush(self) -> None:
        if not self._buf.pcm_bytes:
            return
        wav_bytes = _pcm_to_wav_bytes(bytes(self._buf.pcm_bytes))
        chunk_index = self._buf.chunk_index
        self._buf.pcm_bytes.clear()
        self._buf.chunk_index += 1
        try:
            await self.on_chunk_ready(self.call_id, chunk_index, wav_bytes)
        except Exception:
            log.exception("chunk callback failed for call %s chunk %s", self.call_id, chunk_index)

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        if self._transport:
            self._transport.close()


class _RtpProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_packet: Callable[[bytes], None]):
        self._on_packet = on_packet

    def datagram_received(self, data: bytes, addr) -> None:
        self._on_packet(data)


def _pcm_to_wav_bytes(pcm_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()
