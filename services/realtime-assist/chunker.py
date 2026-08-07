"""
Per-call audio chunker.

Asterisk's ARI External Media feature streams a channel's audio to us as
RTP over UDP once we bridge a Snoop channel into it (see ari_listener.py).
Each active call gets its own dedicated UDP port so incoming packets can be
attributed to the right call_id — Asterisk's external_host only gives us a
destination address, not per-packet call identity, so port-per-call is the
simplest correct way to demux multiple concurrent calls.

Format is `slin` (Asterisk's internal 8kHz mono signed-linear PCM), not
ulaw. ulaw worked for the Local-channel test paths (autotest,
realcalltest) but caused Asterisk to fail transcoding outright ("No
translator path", hundreds/sec) whenever the far end was a real WebRTC/
opus endpoint (1001<->1003) — slin is Asterisk's universal internal
format, so a transcoding path always exists regardless of the call's
actual negotiated codec.

Getting the wire format right took three real, verified iterations, not
guesses:
1. The RTP payload type on this stream is 10, which per RFC 3551's static
   table nominally means L16/44100Hz/stereo. Tried that — a human listener
   described the result as "how rats make sound" (fast, high-pitched
   chattering — the textbook symptom of a sample rate set too high).
2. RFC 3551 also specifies L16 RTP payloads are big-endian (network byte
   order), while WAV/PCM is little-endian — a required byteswap, confirmed
   by testing with actual known call-center audio content:
3. Correct combination, verified by matching a live transcript word-for-
   word against known real call content: **8kHz mono, byteswapped**. RTP
   payload type 10 is apparently just Asterisk's internal marker here, not
   a literal application of RFC 3551's static table — the 44.1kHz/stereo
   reading doesn't apply to this internal stream.

This module owns: binding that per-call UDP socket, buffering packets by
RTP sequence number (UDP doesn't guarantee order, and even rare reordering
would scramble the audio in a way indistinguishable from a wrong-format
bug), byteswapping the L16 payload, and firing a callback with a WAV blob
once ~CHUNK_SECONDS of audio has accumulated.
"""
import asyncio
import audioop
import io
import logging
import wave
from dataclasses import dataclass, field
from typing import Callable, Awaitable

log = logging.getLogger("chunker")

SAMPLE_RATE = 8000  # Asterisk externalMedia format=slin, confirmed live
RTP_HEADER_LEN = 12
CHUNK_SECONDS = 12  # within the agreed 10-15s near-real-time window

ChunkCallback = Callable[[str, int, bytes], Awaitable[None]]


@dataclass
class _CallBuffer:
    # Keyed by RTP sequence number so out-of-order arrivals get sorted
    # correctly at flush time instead of corrupting the audio.
    packets: dict = field(default_factory=dict)
    chunk_index: int = 0


class CallAudioTap:
    """One instance per active call. Binds a UDP socket, buffers RTP
    packets by sequence number, byteswaps them in order, and calls
    `on_chunk_ready(call_id, wav_bytes)` every CHUNK_SECONDS."""

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
        seq = int.from_bytes(data[2:4], "big")
        self._buf.packets[seq] = data[RTP_HEADER_LEN:]

    async def _flush_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(CHUNK_SECONDS)
                await self._flush()
        except asyncio.CancelledError:
            await self._flush()  # flush whatever's left on shutdown
            raise

    async def _flush(self) -> None:
        if not self._buf.packets:
            return
        # Sort by sequence number, not arrival order — see module docstring.
        ordered_payload = b"".join(
            payload for _, payload in sorted(self._buf.packets.items())
        )
        chunk_index = self._buf.chunk_index
        self._buf.packets = {}
        self._buf.chunk_index += 1

        try:
            # RFC 3551: RTP L16 samples are network byte order (big-endian);
            # WAV/PCM is little-endian.
            pcm = audioop.byteswap(ordered_payload, 2)
        except audioop.error:
            log.warning("byteswap failed for call %s chunk %s, skipping",
                        self.call_id, chunk_index)
            return

        wav_bytes = _pcm_to_wav_bytes(pcm)
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
