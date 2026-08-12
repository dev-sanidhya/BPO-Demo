"""Create clearly labelled Hindi two-voice recordings for a controlled demo.

These are synthetic Edge TTS test interactions, not customer calls.  Each
scenario produces separate agent/customer tracks and a stereo mix so the
platform can retain speaker attribution during the controlled replay.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "controlled-hindi-demo-calls"
RATE = 16_000
GAP_MS = 350

SCENARIOS = {
    "good-resolution": [
        ("agent", "नमस्ते, ग्राहक सहायता में आपका स्वागत है। मैं मीरा बोल रही हूँ। कृपया अपना ऑर्डर नंबर बताएँ।", "hi-IN-SwaraNeural"),
        ("customer", "नमस्ते मीरा जी, मेरा ऑर्डर पाँच दिन से नहीं आया है और मुझे कोई अपडेट नहीं मिला।", "hi-IN-MadhurNeural"),
        ("agent", "असुविधा के लिए क्षमा कीजिए। मैं अभी स्थिति जाँचती हूँ। आपका ऑर्डर कल शाम तक पहुँच जाएगा और मैं आपको एसएमएस पुष्टि भेज रही हूँ। क्या मैं और किसी बात में मदद कर सकती हूँ?", "hi-IN-SwaraNeural"),
        ("customer", "नहीं, धन्यवाद। आपने स्पष्ट जानकारी दी और मेरी समस्या हल हो गई।", "hi-IN-MadhurNeural"),
    ],
    "coaching-needed": [
        ("agent", "हाँ, बोलिए।", "hi-IN-SwaraNeural"),
        ("customer", "मेरा ऑर्डर पाँच दिन से नहीं आया है। मुझे कोई अपडेट नहीं मिला और यह बहुत जरूरी है।", "hi-IN-MadhurNeural"),
        ("agent", "देरी है तो इंतज़ार कीजिए। अभी मैं कुछ नहीं कर सकती।", "hi-IN-SwaraNeural"),
        ("customer", "मुझे कम से कम डिलीवरी की तारीख और शिकायत दर्ज करने का तरीका बताइए।", "hi-IN-MadhurNeural"),
        ("agent", "पता नहीं। बाद में कॉल कर लेना।", "hi-IN-SwaraNeural"),
        ("customer", "ठीक है, मैं बहुत निराश हूँ।", "hi-IN-MadhurNeural"),
    ],
}


def read_mono_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() != RATE:
            raise ValueError(f"Expected 16kHz 16-bit mono WAV: {path}")
        return source.readframes(source.getnframes())


def write_mono_wav(path: Path, frames: bytes) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(frames)


async def build_scenario(name: str, turns: list[tuple[str, str, str]]) -> dict:
    scenario_dir = OUTPUT / name
    scenario_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{name}-") as temp_name:
        temp = Path(temp_name)
        rendered: list[tuple[str, str, bytes]] = []
        for index, (speaker, text, voice) in enumerate(turns):
            mp3 = temp / f"{index}.mp3"
            wav = temp / f"{index}.wav"
            await edge_tts.Communicate(text, voice).save(str(mp3))
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
            rendered.append((speaker, text, read_mono_wav(wav)))

    tracks = {"agent": bytearray(), "customer": bytearray()}
    segments: list[dict] = []
    cursor_ms = 0
    silence = b"\x00\x00" * round(RATE * GAP_MS / 1000)
    for index, (speaker, text, frames) in enumerate(rendered):
        duration_ms = round(len(frames) / 2 / RATE * 1000)
        turn_path = scenario_dir / f"turn-{index:02d}-{speaker}.wav"
        write_mono_wav(turn_path, frames)
        segments.append({"speaker": speaker, "text": text, "start_ms": cursor_ms, "end_ms": cursor_ms + duration_ms, "file": turn_path.name})
        for track_speaker, track in tracks.items():
            track.extend(frames if track_speaker == speaker else b"\x00" * len(frames))
            track.extend(silence)
        cursor_ms += duration_ms + GAP_MS

    agent_path = scenario_dir / "agent.wav"
    customer_path = scenario_dir / "customer.wav"
    mix_path = scenario_dir / "stereo-call.wav"
    write_mono_wav(agent_path, bytes(tracks["agent"]))
    write_mono_wav(customer_path, bytes(tracks["customer"]))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(agent_path), "-i", str(customer_path), "-filter_complex", "[0:a][1:a]amerge=inputs=2", "-ac", "2", "-c:a", "pcm_s16le", str(mix_path)], check=True)
    manifest = {"classification": "controlled_synthetic_demo", "language": "hi", "voices": {"agent": "hi-IN-SwaraNeural", "customer": "hi-IN-MadhurNeural"}, "duration_ms": cursor_ms, "segments": segments}
    (scenario_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"scenario": name, "duration_ms": cursor_ms, "recording": str(mix_path)}


async def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    results = [await build_scenario(name, turns) for name, turns in SCENARIOS.items()]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
