"""Create clearly labelled Hindi two-voice recordings for a controlled demo.

These are synthetic Edge TTS test interactions, not customer calls.  Each
scenario produces separate agent/customer tracks and a stereo mix so the
platform can retain speaker attribution during the controlled replay.
"""

from __future__ import annotations

import asyncio
import argparse
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
    "partial-resolution": [
        ("agent", "नमस्ते, ग्राहक सहायता से मीरा बोल रही हूँ। मैं आपकी मदद करती हूँ।", "hi-IN-SwaraNeural"),
        ("customer", "मेरे रिफंड का अभी तक कोई संदेश नहीं आया है।", "hi-IN-MadhurNeural"),
        ("agent", "मैंने आपका रिफंड अनुरोध देख लिया है। यह दो कार्य दिवस में पूरा होना चाहिए।", "hi-IN-SwaraNeural"),
        ("customer", "ठीक है।", "hi-IN-MadhurNeural"),
    ],
    "privacy-risk": [
        ("agent", "नमस्ते, ग्राहक सहायता से मीरा बोल रही हूँ। मैं आपकी मदद करती हूँ।", "hi-IN-SwaraNeural"),
        ("customer", "मेरे खाते में एक अनजान लेनदेन दिख रहा है।", "hi-IN-MadhurNeural"),
        ("agent", "पहले अपना पूरा कार्ड नंबर और ओटीपी बता दीजिए, फिर मैं देखती हूँ।", "hi-IN-SwaraNeural"),
        ("customer", "मुझे यह सुरक्षित नहीं लग रहा।", "hi-IN-MadhurNeural"),
    ],
    "professional-escalation": [
        ("agent", "नमस्ते, ग्राहक सहायता में आपका स्वागत है। मैं मीरा बोल रही हूँ। मैं आपकी समस्या समझना चाहती हूँ।", "hi-IN-SwaraNeural"),
        ("customer", "मेरी शिकायत तीन दिन से लंबित है और मुझे समाधान चाहिए।", "hi-IN-MadhurNeural"),
        ("agent", "देरी के लिए क्षमा कीजिए। मैं इसे अभी प्राथमिकता के साथ वरिष्ठ टीम को भेज रही हूँ और आज शाम तक आपको स्थिति की जानकारी दूँगी। क्या मैं किसी और बात में मदद कर सकती हूँ?", "hi-IN-SwaraNeural"),
        ("customer", "नहीं, धन्यवाद।", "hi-IN-MadhurNeural"),
    ],
    "abrupt-close": [
        ("agent", "नमस्ते, ग्राहक सहायता से मीरा बोल रही हूँ।", "hi-IN-SwaraNeural"),
        ("customer", "मेरा पैकेज गलत पते पर चला गया है।", "hi-IN-MadhurNeural"),
        ("agent", "ठीक है, बाद में देखेंगे।", "hi-IN-SwaraNeural"),
        ("customer", "कृपया कोई शिकायत नंबर तो दीजिए।", "hi-IN-MadhurNeural"),
        ("agent", "अभी नहीं।", "hi-IN-SwaraNeural"),
    ],
    "marathi-resolution": [
        ("agent", "नमस्कार, ग्राहक सेवेत आपले स्वागत आहे. मी आरोही बोलत आहे. मी कशी मदत करू?", "mr-IN-AarohiNeural"),
        ("customer", "माझी ऑर्डर अजून आली नाही आणि मला विलंबाचे कारण समजले नाही.", "mr-IN-ManoharNeural"),
        ("agent", "विलंबाबद्दल क्षमस्व. तुमची ऑर्डर उद्या संध्याकाळपर्यंत पोहोचेल. मी तुम्हाला संदेशाने पुष्टी पाठवते. आणखी काही मदत हवी आहे का?", "mr-IN-AarohiNeural"),
        ("customer", "नाही, धन्यवाद. माहिती स्पष्ट होती.", "mr-IN-ManoharNeural"),
    ],
    "marathi-escalation": [
        ("agent", "नमस्कार, ग्राहक सेवेत आपले स्वागत आहे. मी आरोही बोलत आहे.", "mr-IN-AarohiNeural"),
        ("customer", "माझी तक्रार तीन दिवसांपासून प्रलंबित आहे आणि मला तातडीचा उपाय हवा आहे.", "mr-IN-ManoharNeural"),
        ("agent", "असुविधेबद्दल क्षमस्व. मी ही तक्रार वरिष्ठ टीमकडे तातडीने पाठवत आहे आणि आज संध्याकाळपर्यंत स्थितीची माहिती देईन. आणखी काही मदत हवी आहे का?", "mr-IN-AarohiNeural"),
        ("customer", "नाही, धन्यवाद.", "mr-IN-ManoharNeural"),
    ],
    "hindi-followup-gap": [
        ("agent", "नमस्ते, ग्राहक सहायता से मीरा बोल रही हूँ। मैं आपकी मदद करती हूँ।", "hi-IN-SwaraNeural"),
        ("customer", "मेरा रिफंड अभी तक नहीं आया है और मुझे स्थिति जाननी है।", "hi-IN-MadhurNeural"),
        ("agent", "मैंने अनुरोध देख लिया है। टीम इस पर काम कर रही है।", "hi-IN-SwaraNeural"),
        ("customer", "मुझे समय सीमा और अगला कदम बताइए।", "hi-IN-MadhurNeural"),
        ("agent", "अभी मेरे पास और जानकारी नहीं है।", "hi-IN-SwaraNeural"),
    ],
    "english-service-recovery": [
        ("agent", "Hello, you have reached customer support. This is Meera. How may I help you?", "en-IN-NeerjaNeural"),
        ("customer", "My delivery was missed twice and I need a confirmed resolution today.", "en-IN-PrabhatNeural"),
        ("agent", "I am sorry for the repeated inconvenience. I have escalated this for priority delivery tomorrow and will send a confirmation today. Is there anything else I can help with?", "en-IN-NeerjaNeural"),
        ("customer", "No, thank you for taking ownership.", "en-IN-PrabhatNeural"),
    ],
    "natural-english-resolution": [
        ("agent", "Hi, thanks for calling customer support. This is Ava. How can I help today?", "en-US-AvaNeural"),
        ("customer", "Hi Ava. My replacement order is showing as delayed and I need it before the weekend.", "en-US-AndrewNeural"),
        ("agent", "I understand. I have checked the order and it is now scheduled for delivery tomorrow. I will send the confirmation as soon as we end this call. Is there anything else you need from me?", "en-US-AvaNeural"),
        ("customer", "No, that solves it. Thanks for being clear about it.", "en-US-AndrewNeural"),
    ],
    "natural-english-coaching": [
        ("agent", "Hello. What is the problem?", "en-US-AvaNeural"),
        ("customer", "I was charged twice for the same order and I need help getting the duplicate charge reversed.", "en-US-AndrewNeural"),
        ("agent", "That is not something I can deal with. You will have to wait and see.", "en-US-AvaNeural"),
        ("customer", "Can you at least tell me what happens next or give me a case number?", "en-US-AndrewNeural"),
        ("agent", "No, just call again later.", "en-US-AvaNeural"),
    ],
}

SCENARIO_LANGUAGES = {
    "marathi-resolution": "mr",
    "marathi-escalation": "mr",
    "english-service-recovery": "en",
    "natural-english-resolution": "en",
    "natural-english-coaching": "en",
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
    mono_path = scenario_dir / "demo-call.wav"
    write_mono_wav(agent_path, bytes(tracks["agent"]))
    write_mono_wav(customer_path, bytes(tracks["customer"]))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(agent_path), "-i", str(customer_path), "-filter_complex", "[0:a][1:a]amerge=inputs=2", "-ac", "2", "-c:a", "pcm_s16le", str(mix_path)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mix_path), "-ac", "1", "-c:a", "pcm_s16le", str(mono_path)], check=True)
    manifest = {"classification": "controlled_synthetic_demo", "language": SCENARIO_LANGUAGES.get(name, "hi"), "duration_ms": cursor_ms, "segments": segments}
    (scenario_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"scenario": name, "duration_ms": cursor_ms, "recording": str(mono_path)}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenarios", nargs="*", default=list(SCENARIOS), choices=list(SCENARIOS))
    parser.add_argument("--clean", action="store_true", help="Remove all generated controlled-demo assets first.")
    args = parser.parse_args()
    if args.clean and OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    results = [await build_scenario(name, SCENARIOS[name]) for name in args.scenarios]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
