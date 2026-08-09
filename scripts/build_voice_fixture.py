"""Build the deterministic two-speaker pilot call and its exact timing manifest."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import wave

import pyttsx3


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "asterisk" / "test-audio" / "deterministic-pilot.wav"
MANIFEST = ROOT / "asterisk" / "test-audio" / "deterministic-pilot.json"
UTTERANCES = [
    ("agent", "Thank you for calling customer care. My name is Aarav. How may I help you?"),
    ("customer", "I have been waiting for my order and nobody has explained the delay."),
    ("agent", "I am sorry about the delay. May I confirm your order reference?"),
    ("customer", "It is O R D two zero four eight."),
    ("agent", "Thank you. The dispatch was delayed, but it is now scheduled for tomorrow. I will send the update by S M S."),
    ("customer", "That answers my question. Thank you."),
]


def synthesize(path: Path, text: str, voice_hint: str) -> None:
    engine = pyttsx3.init()
    engine.setProperty("rate", 165)
    for voice in engine.getProperty("voices"):
        if voice_hint.lower() in voice.name.lower():
            engine.setProperty("voice", voice.id)
            break
    engine.save_to_file(text, str(path))
    engine.runAndWait()
    engine.stop()


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    frames: list[bytes] = []
    elapsed_frames = 0
    parameters = None
    with tempfile.TemporaryDirectory(prefix="aperture-voice-") as temp:
        temp_dir = Path(temp)
        for index, (speaker, text) in enumerate(UTTERANCES):
            clip = temp_dir / f"{index}.wav"
            synthesize(clip, text, "David" if speaker == "agent" else "Zira")
            with wave.open(str(clip), "rb") as audio:
                current = audio.getparams()
                if parameters is None:
                    parameters = current
                elif (current.nchannels, current.sampwidth, current.framerate) != (parameters.nchannels, parameters.sampwidth, parameters.framerate):
                    raise RuntimeError("TTS voices produced incompatible WAV formats")
                clip_frames = audio.readframes(current.nframes)
                start_ms = round(elapsed_frames / current.framerate * 1000)
                frames.append(clip_frames)
                elapsed_frames += current.nframes
                end_ms = round(elapsed_frames / current.framerate * 1000)
                manifest.append({"speaker": speaker, "text": text, "start_ms": start_ms, "end_ms": end_ms, "language": "en", "confidence": 100})
                silence_frames = round(current.framerate * 0.35)
                frames.append(b"\x00" * silence_frames * current.sampwidth * current.nchannels)
                elapsed_frames += silence_frames
    if parameters is None:
        raise RuntimeError("No audio was generated")
    with wave.open(str(OUTPUT), "wb") as output:
        output.setnchannels(parameters.nchannels)
        output.setsampwidth(parameters.sampwidth)
        output.setframerate(parameters.framerate)
        output.writeframes(b"".join(frames))
    MANIFEST.write_text(json.dumps({"segments": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} and {MANIFEST}")


if __name__ == "__main__":
    main()
