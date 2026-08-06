"""Turns a ~12s audio chunk into (optionally) a short live nudge for the
agent. Two Groq calls per chunk: fast transcription, then a fast, cheap LLM
call that decides whether the agent needs a nudge right now at all — most
chunks of a healthy call should produce no prompt, only real signal."""
import json
import logging
import os

from groq import Groq

log = logging.getLogger("prompt_engine")

_client: Groq | None = None

NUDGE_SYSTEM_PROMPT = """You are a real-time call coaching assistant listening
to a live customer support call, one ~12 second chunk at a time. You will be
given the latest chunk's transcript. Decide if the agent needs a short,
actionable nudge right now (e.g. missed a compliance step, tone is off,
customer sounds frustrated and needs acknowledgement, agent is rambling off
script). Most chunks need no nudge — say nothing unless it's genuinely
useful. Respond with ONLY JSON: {"suggestion": "<short imperative nudge>"}
or {"suggestion": null} if no nudge is warranted. Keep any suggestion under
15 words, phrased as a direct instruction to the agent (e.g. "Acknowledge
their frustration before continuing.")."""


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def transcribe_chunk(wav_bytes: bytes) -> str:
    result = _get_client().audio.transcriptions.create(
        file=("chunk.wav", wav_bytes),
        model="whisper-large-v3-turbo",
        response_format="text",
    )
    return str(result).strip()


def maybe_generate_nudge(transcript_chunk: str) -> str | None:
    if not transcript_chunk:
        return None
    try:
        completion = _get_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": NUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": transcript_chunk},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        parsed = json.loads(completion.choices[0].message.content)
        return parsed.get("suggestion")
    except Exception:
        log.exception("nudge generation failed, skipping this chunk")
        return None
