"""Generate clearly labelled synthetic multilingual support-call fixtures.

Requires `edge-tts` and `ffmpeg`. These files are demo/ASR regression assets,
not evidence of performance on the prospect's real calls.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import wave

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "asterisk" / "test-audio"

CALLS = {
    "hi": [
        ("agent", "नमस्कार, ग्राहक सहायता में आपका स्वागत है। मैं मीरा बोल रही हूँ। मैं आपकी कैसे मदद कर सकती हूँ?", "hi-IN-SwaraNeural"),
        ("customer", "मेरा ऑर्डर अभी तक नहीं आया और मुझे देरी की कोई जानकारी नहीं मिली।", "hi-IN-MadhurNeural"),
        ("agent", "देरी के लिए मुझे खेद है। कृपया अपना ऑर्डर नंबर बताइए।", "hi-IN-SwaraNeural"),
        ("customer", "ऑर्डर नंबर ओ आर डी दो शून्य चार आठ है।", "hi-IN-MadhurNeural"),
        ("agent", "धन्यवाद। डिलीवरी कल के लिए तय है और मैं एस एम एस से पुष्टि भेज रही हूँ।", "hi-IN-SwaraNeural"),
        ("customer", "ठीक है, इससे मेरी समस्या हल हो गई। धन्यवाद।", "hi-IN-MadhurNeural"),
    ],
    "mr": [
        ("agent", "नमस्कार, ग्राहक सेवेत आपले स्वागत आहे. मी आरोही बोलत आहे. मी आपली कशी मदत करू?", "mr-IN-AarohiNeural"),
        ("customer", "माझी ऑर्डर अजून आली नाही आणि मला विलंबाची कोणतीही माहिती मिळाली नाही.", "mr-IN-ManoharNeural"),
        ("agent", "विलंबाबद्दल क्षमस्व. कृपया आपला ऑर्डर क्रमांक सांगा.", "mr-IN-AarohiNeural"),
        ("customer", "ऑर्डर क्रमांक ओ आर डी दोन शून्य चार आठ आहे.", "mr-IN-ManoharNeural"),
        ("agent", "धन्यवाद. डिलिव्हरी उद्यासाठी निश्चित आहे आणि मी एस एम एसने पुष्टी पाठवत आहे.", "mr-IN-AarohiNeural"),
        ("customer", "ठीक आहे, माझी समस्या सुटली. धन्यवाद.", "mr-IN-ManoharNeural"),
    ],
    "hi-en": [
        ("agent", "Thank you for calling. मैं मीरा बोल रही हूँ. How may I help you?", "hi-IN-SwaraNeural"),
        ("customer", "मेरा order अभी तक नहीं आया and nobody shared an update.", "hi-IN-MadhurNeural"),
        ("agent", "Delay के लिए I am sorry. Please अपना order reference confirm कर दीजिए.", "hi-IN-SwaraNeural"),
        ("customer", "Order number ओ आर डी two zero four eight है.", "hi-IN-MadhurNeural"),
        ("agent", "Thank you. Delivery कल scheduled है and I will send an SMS confirmation.", "hi-IN-SwaraNeural"),
        ("customer", "That works, मेरी problem solve हो गई. Thank you.", "hi-IN-MadhurNeural"),
    ],
}


def duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as audio:
        return round(audio.getnframes() / audio.getframerate() * 1000)


async def generate() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bpo-multilingual-") as temp_name:
        temp = Path(temp_name)
        silence = temp / "silence.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.35", "-c:a", "pcm_s16le", str(silence)], check=True)
        for language, turns in CALLS.items():
            segments: list[dict] = []
            concat: list[Path] = []
            cursor = 0
            for index, (speaker, text, voice) in enumerate(turns):
                mp3 = temp / f"{language}-{index}.mp3"
                wav = temp / f"{language}-{index}.wav"
                await edge_tts.Communicate(text, voice).save(str(mp3))
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
                turn_duration = duration_ms(wav)
                segments.append({"speaker": speaker, "text": text, "start_ms": cursor, "end_ms": cursor + turn_duration})
                concat.extend([wav, silence])
                cursor += turn_duration + 350
            list_file = temp / f"{language}-concat.txt"
            list_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in concat), encoding="utf-8")
            target = OUTPUT / f"synthetic-support-{language}.wav"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(target)], check=True)
            (OUTPUT / f"synthetic-support-{language}.json").write_text(json.dumps({"source": "synthetic_edge_tts", "language": language, "segments": segments}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Generated {target.name}: {duration_ms(target)} ms")


if __name__ == "__main__":
    asyncio.run(generate())
