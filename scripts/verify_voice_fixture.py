"""Fail if the deterministic recording and speaker manifest drift apart."""

from __future__ import annotations

import json
from pathlib import Path
import wave


root = Path(__file__).resolve().parents[1]
audio_path = root / "asterisk" / "test-audio" / "deterministic-pilot.wav"
manifest_path = root / "asterisk" / "test-audio" / "deterministic-pilot.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["segments"]
with wave.open(str(audio_path), "rb") as audio:
    duration_ms = round(audio.getnframes() / audio.getframerate() * 1000)

assert manifest, "manifest has no segments"
assert {segment["speaker"] for segment in manifest} == {"agent", "customer"}
assert all(segment["start_ms"] < segment["end_ms"] for segment in manifest)
assert all(left["end_ms"] <= right["start_ms"] for left, right in zip(manifest, manifest[1:]))
assert manifest[-1]["end_ms"] <= duration_ms <= manifest[-1]["end_ms"] + 1000
print({"ok": True, "duration_ms": duration_ms, "segments": len(manifest), "speakers": sorted({segment["speaker"] for segment in manifest})})
