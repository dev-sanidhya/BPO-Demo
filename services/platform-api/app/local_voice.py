from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import wave

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AssistEvent, Conversation, CostEvent, QAAnswer, QAEvaluation, QAForm, QAQuestion, Recording, SurveyResponse, TranscriptSegment


TRANSCRIPTS: dict[str, list[tuple[str, str, int, int]]] = {
    "en": [
        ("agent", "Thank you for calling customer care. My name is Aarav. How may I help you?", 0, 6200),
        ("customer", "I have been waiting for my order and nobody has explained the delay.", 6500, 13200),
        ("agent", "I am sorry about the delay. May I confirm your order reference?", 13600, 19000),
        ("customer", "It is ORD-2048.", 19400, 21800),
        ("agent", "Thank you. The dispatch was delayed, but it is now scheduled for tomorrow. I will send the update by SMS.", 22200, 32200),
        ("customer", "That answers my question, thank you.", 32600, 36600),
    ],
    "hi": [
        ("agent", "नमस्कार, ग्राहक सहायता में आपका स्वागत है। मैं आरव बोल रहा हूँ।", 0, 6200),
        ("customer", "मेरा ऑर्डर अभी तक नहीं आया और मुझे कोई जानकारी नहीं मिली।", 6500, 13200),
        ("agent", "देरी के लिए मुझे खेद है। कृपया अपना ऑर्डर नंबर बताइए।", 13600, 19000),
        ("customer", "ऑर्डर नंबर ORD-2048 है।", 19400, 21800),
        ("agent", "धन्यवाद। डिलीवरी कल के लिए तय है और मैं SMS से पुष्टि भेज रहा हूँ।", 22200, 32200),
        ("customer", "ठीक है, धन्यवाद।", 32600, 36600),
    ],
    "mr": [
        ("agent", "नमस्कार, ग्राहक सेवेत आपले स्वागत आहे. मी आरव बोलत आहे.", 0, 6200),
        ("customer", "माझी ऑर्डर अजून आली नाही आणि मला काही माहिती मिळाली नाही.", 6500, 13200),
        ("agent", "विलंबाबद्दल क्षमस्व. कृपया ऑर्डर क्रमांक सांगा.", 13600, 19000),
        ("customer", "ऑर्डर क्रमांक ORD-2048 आहे.", 19400, 21800),
        ("agent", "धन्यवाद. डिलिव्हरी उद्यासाठी निश्चित आहे आणि मी SMS पाठवत आहे.", 22200, 32200),
        ("customer", "ठीक आहे, धन्यवाद.", 32600, 36600),
    ],
    "hi-en": [
        ("agent", "Thank you for calling. Main Aarav bol raha hoon, how may I help?", 0, 6200),
        ("customer", "Mera order abhi tak nahi aaya and nobody shared an update.", 6500, 13200),
        ("agent", "Delay ke liye I am sorry. Please order reference confirm kar dijiye.", 13600, 19000),
        ("customer", "It is ORD-2048.", 19400, 21800),
        ("agent", "Thank you. Delivery kal scheduled hai and I will send an SMS confirmation.", 22200, 32200),
        ("customer", "That works, thank you.", 32600, 36600),
    ],
}


def voice_fixture_paths(language: str) -> tuple[Path, Path]:
    settings = get_settings()
    if language in {"hi", "mr", "hi-en"}:
        fixture_dir = Path(settings.voice_fixture_path).parent
        audio = fixture_dir / f"synthetic-support-{language}.wav"
        manifest = fixture_dir / f"synthetic-support-{language}.json"
        if audio.is_file() and manifest.is_file():
            return audio, manifest
    return Path(settings.voice_fixture_path), Path(settings.voice_fixture_manifest_path)


def _write_recording(conversation_id: str, language: str) -> tuple[str, int, str, int]:
    settings = get_settings()
    output_dir = Path(settings.recording_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{conversation_id}.wav"
    fixture, _ = voice_fixture_paths(language)
    if fixture.exists():
        shutil.copyfile(fixture, destination)
    else:
        with wave.open(str(destination), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 8_000 * 40)
    with wave.open(str(destination), "rb") as audio:
        duration_ms = int(audio.getnframes() / audio.getframerate() * 1000)
        channels = audio.getnchannels()
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return str(destination), duration_ms, digest, channels


def finalize_local_voice(db: Session, conversation: Conversation) -> None:
    if db.scalar(select(Recording).where(Recording.conversation_id == conversation.id)):
        return

    storage_key, duration_ms, digest, channels = _write_recording(conversation.id, conversation.language)
    db.add(Recording(tenant_id=conversation.tenant_id, conversation_id=conversation.id, storage_key=storage_key, duration_ms=duration_ms, sha256=digest, channels=channels))

    language = conversation.language if conversation.language in TRANSCRIPTS else "en"
    transcript = TRANSCRIPTS[language]
    confidence = 96
    _, manifest = voice_fixture_paths(language)
    if manifest.exists():
        source_segments = json.loads(manifest.read_text(encoding="utf-8"))["segments"]
        transcript = [(item["speaker"], item["text"], item["start_ms"], item["end_ms"]) for item in source_segments]
        confidence = 100
    for speaker, text, start_ms, end_ms in transcript:
        db.add(TranscriptSegment(tenant_id=conversation.tenant_id, conversation_id=conversation.id, speaker=speaker, text=text, start_ms=start_ms, end_ms=end_ms, language=language, confidence=confidence))

    db.add(AssistEvent(tenant_id=conversation.tenant_id, conversation_id=conversation.id, event_type="compliance", title="Identity check", content="Confirm the order reference before sharing account details.", evidence_start_ms=6500, evidence_end_ms=13200, metadata_json={"source": "local_rules_v1"}))
    db.add(AssistEvent(tenant_id=conversation.tenant_id, conversation_id=conversation.id, event_type="next_best_action", title="Acknowledge and resolve", content="Acknowledge the delay, confirm the reference, then state the delivery commitment.", evidence_start_ms=6500, evidence_end_ms=13200, metadata_json={"source": "local_rules_v1"}))
    db.add(AssistEvent(tenant_id=conversation.tenant_id, conversation_id=conversation.id, event_type="knowledge", title="Delayed dispatch policy", content="When dispatch is delayed, provide the revised date and send written confirmation.", evidence_start_ms=22200, evidence_end_ms=32200, metadata_json={"article": "Delayed dispatch"}))

    form = db.scalar(select(QAForm).where(QAForm.tenant_id == conversation.tenant_id, QAForm.active.is_(True)).order_by(QAForm.version.desc()))
    if form:
        questions = list(db.scalars(select(QAQuestion).where(QAQuestion.form_id == form.id).order_by(QAQuestion.position)))
        evaluation = QAEvaluation(tenant_id=conversation.tenant_id, conversation_id=conversation.id, form_id=form.id, automatic_score=88, fatal_triggered=False, provider="local_rules", model="deterministic-pilot-v1", rubric_version=form.version, summary="The agent acknowledged the delay, verified the order reference, and gave a clear resolution.")
        db.add(evaluation)
        db.flush()
        evidence = [transcript[0], transcript[2], transcript[4]]
        for index, question in enumerate(questions):
            speaker, quote, start_ms, end_ms = evidence[min(index, len(evidence) - 1)]
            db.add(QAAnswer(evaluation_id=evaluation.id, question_id=question.id, passed=True, score=100, confidence=96, evidence_quote=quote, evidence_start_ms=start_ms, evidence_end_ms=end_ms, reasoning=f"Rule matched the required step in the {speaker} segment."))

    db.add(SurveyResponse(tenant_id=conversation.tenant_id, conversation_id=conversation.id, actual_csat=None, predicted_satisfaction_risk=18, source="predicted_local_v1"))
    for category, provider, units, unit_name, cost in [
        ("telephony", "deterministic_local", max(duration_ms // 1000, 1), "seconds", 0),
        ("transcription", "local_fixture", max(duration_ms // 1000, 1), "audio_seconds", 0),
        ("inference", "local_rules", len(transcript), "segments", 0),
        ("storage", "local_disk", Path(storage_key).stat().st_size, "bytes", 0),
    ]:
        db.add(CostEvent(tenant_id=conversation.tenant_id, conversation_id=conversation.id, category=category, provider=provider, units=units, unit_name=unit_name, cost_micros_inr=cost))

    conversation.summary = "Customer called about a delayed order. The agent verified ORD-2048, confirmed delivery for tomorrow, and promised an SMS update."
    conversation.ended_at = datetime.now(timezone.utc)
