"""Thin wrapper around the Groq SDK for transcription and QA scoring."""
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


def transcribe_file(path: str) -> str:
    """Full post-call transcription. Quality matters more than speed here,
    so we use the same whisper-large-v3-turbo model as real-time (it's both
    fast and accurate) rather than trading accuracy for extra speed."""
    with open(path, "rb") as f:
        result = client().audio.transcriptions.create(
            file=(os.path.basename(path), f.read()),
            model="whisper-large-v3-turbo",
            response_format="text",
        )
    return str(result)


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
