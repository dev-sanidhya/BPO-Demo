"""Thin wrapper around the Groq SDK for QA scoring. Transcription itself
happens in the realtime-assist service (see services/realtime-assist/
prompt_engine.py) — qa-scoring scores the transcript chunks it already
wrote to Postgres rather than re-transcribing audio."""
import json
import os

from groq import Groq

_client: Groq | None = None


def client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ["GROQ_API_KEY"]
        _client = Groq(api_key=api_key)
    return _client


def score_transcript(transcript: str, rubric_prompt: str) -> dict:
    """Runs the QA rubric against a full call transcript. Uses the larger
    70B model since this is async/offline and reasoning quality matters
    more than latency."""
    completion = client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": rubric_prompt},
            {"role": "user", "content": f"Call transcript:\n\n{transcript}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    raw = completion.choices[0].message.content
    return json.loads(raw)
