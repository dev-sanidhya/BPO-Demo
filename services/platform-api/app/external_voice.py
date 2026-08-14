from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import wave

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from .ai import GroqAI, estimate_asr_cost_micros_inr, estimate_llm_cost_micros_inr, retrieve_knowledge
from .config import get_settings
from .local_voice import voice_fixture_paths
from .models import AssistEvent, Conversation, CostEvent, KnowledgeArticle, QAAnswer, QAEvaluation, QAForm, QAQuestion, Recording, Script, SurveyResponse, TranscriptSegment


def _campaign_scope(statement, model, conversation: Conversation):
    """Prefer the call's campaign material, with tenant-global material as a fallback."""
    statement = statement.where(model.tenant_id == conversation.tenant_id, model.active.is_(True))
    if conversation.campaign_id is None:
        return statement.where(model.campaign_id.is_(None))
    return statement.where(or_(model.campaign_id == conversation.campaign_id, model.campaign_id.is_(None))).order_by((model.campaign_id == conversation.campaign_id).desc())


def _ensure_recording(db: Session, conversation: Conversation) -> tuple[Recording, Path | None]:
    existing = db.scalar(select(Recording).where(Recording.conversation_id == conversation.id))
    if existing:
        return existing, None
    settings = get_settings()
    fixture, manifest = voice_fixture_paths(conversation.language)
    if not fixture.is_file():
        raise RuntimeError("No captured or fixture voice recording is available")
    destination = Path(settings.recording_dir) / f"{conversation.id}.wav"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture, destination)
    with wave.open(str(destination), "rb") as audio:
        duration_ms = round(audio.getnframes() / audio.getframerate() * 1000)
        channels = audio.getnchannels()
    recording = Recording(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        storage_key=str(destination),
        mime_type="audio/wav",
        duration_ms=duration_ms,
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        channels=channels,
    )
    db.add(recording)
    db.flush()
    return recording, manifest


def _fixture_segments(transcription, manifest: Path | None) -> list[dict] | None:
    if manifest is None or not manifest.is_file() or not transcription.words:
        return None
    try:
        turns = json.loads(manifest.read_text(encoding="utf-8"))["segments"]
    except (OSError, KeyError, ValueError, TypeError):
        return None
    result: list[dict] = []
    for turn in turns:
        words = [item["word"] for item in transcription.words if int(turn["start_ms"]) <= (item["start_ms"] + item["end_ms"]) // 2 <= int(turn["end_ms"])]
        if words:
            result.append({"text": " ".join(words), "start_ms": int(turn["start_ms"]), "end_ms": int(turn["end_ms"]), "avg_logprob": -0.15, "no_speech_prob": 0.0, "speaker": str(turn["speaker"])})
    return result or None


def _confidence(avg_logprob: float, no_speech_prob: float) -> int:
    # This is an explicitly labelled display heuristic, not calibrated ASR probability.
    value = 100 + avg_logprob * 20 - no_speech_prob * 40
    return max(1, min(round(value), 99))


def finalize_external_voice(db: Session, conversation: Conversation) -> None:
    if db.scalar(select(QAEvaluation).where(QAEvaluation.conversation_id == conversation.id, QAEvaluation.provider == "groq")):
        return
    settings = get_settings()
    recording, fixture_manifest = _ensure_recording(db, conversation)
    provider = GroqAI(settings)
    live_rows = list(db.scalars(select(TranscriptSegment).where(TranscriptSegment.conversation_id == conversation.id).order_by(TranscriptSegment.start_ms, TranscriptSegment.created_at)))
    use_live_segments = bool(live_rows) and all(row.speaker in {"agent", "customer"} for row in live_rows)
    segments: list[dict] = []
    transcription = None
    if use_live_segments:
        segments = [{"speaker": row.speaker, "text": row.text, "start_ms": row.start_ms, "end_ms": row.end_ms, "language": row.language, "confidence": row.confidence} for row in live_rows]
    else:
        transcription = provider.transcribe(recording.storage_key, settings.groq_final_asr_model, conversation.language)
        db.execute(delete(TranscriptSegment).where(TranscriptSegment.conversation_id == conversation.id))
        source_segments = _fixture_segments(transcription, fixture_manifest) or [{**item, "speaker": "unknown"} for item in transcription.segments]
        for item in source_segments:
            segment = {
                **item,
                "speaker": item["speaker"],
                "language": conversation.language if conversation.language != "auto" else transcription.language,
                "confidence": _confidence(item["avg_logprob"], item["no_speech_prob"]),
            }
            segments.append(segment)
            db.add(TranscriptSegment(
                tenant_id=conversation.tenant_id,
                conversation_id=conversation.id,
                speaker=segment["speaker"],
                text=segment["text"],
                start_ms=segment["start_ms"],
                end_ms=segment["end_ms"],
                language=segment["language"],
                confidence=segment["confidence"],
            ))
    if not segments:
        raise RuntimeError("Groq returned no speech segments")

    script = db.scalar(_campaign_scope(select(Script), Script, conversation).order_by(Script.version.desc()))
    articles = list(db.scalars(_campaign_scope(select(KnowledgeArticle), KnowledgeArticle, conversation)))
    transcript_text = " ".join(item["text"] for item in segments)
    retrieved = retrieve_knowledge(transcript_text, [{"title": item.title, "content": item.content, "tags": item.tags} for item in articles])
    form = db.scalar(_campaign_scope(select(QAForm), QAForm, conversation).order_by(QAForm.version.desc()))
    questions = list(db.scalars(select(QAQuestion).where(QAQuestion.form_id == form.id).order_by(QAQuestion.position))) if form else []
    question_payload = [{"id": item.id, "label": item.label, "guidance": item.guidance, "weight": item.weight, "fatal": item.fatal} for item in questions]
    analysis = provider.analyze(
        segments,
        question_payload,
        script.content if script else "Use professional customer-service practices.",
        retrieved,
        conversation.language,
    )
    payload = analysis.payload
    for item in payload["assists"][:5]:
        index = max(0, min(int(item["evidence_segment_index"]), len(segments) - 1))
        evidence = segments[index]
        db.add(AssistEvent(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            event_type=item["event_type"],
            title=item["title"][:160],
            content=item["content"],
            evidence_start_ms=evidence["start_ms"],
            evidence_end_ms=evidence["end_ms"],
            metadata_json={"source": "groq", "model": settings.groq_qa_model, "request_id": analysis.request_id, "retrieved_articles": [article["title"] for article in retrieved]},
        ))

    if form:
        by_id = {item.id: item for item in questions}
        answers = [item for item in payload["qa_answers"] if item["question_id"] in by_id]
        answered = {item["question_id"] for item in answers}
        if answered != set(by_id):
            raise RuntimeError("Groq QA response did not cover the configured rubric")
        total_weight = sum(item.weight for item in questions) or 1
        weighted_score = round(sum(max(0, min(int(item["score"]), 100)) * by_id[item["question_id"]].weight for item in answers) / total_weight)
        fatal_triggered = any(not item["passed"] and by_id[item["question_id"]].fatal for item in answers)
        evaluation = QAEvaluation(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            form_id=form.id,
            automatic_score=weighted_score,
            fatal_triggered=fatal_triggered,
            provider="groq",
            model=settings.groq_qa_model,
            rubric_version=form.version,
            summary=payload["summary"],
        )
        db.add(evaluation)
        db.flush()
        for item in answers:
            index = max(0, min(int(item["evidence_segment_index"]), len(segments) - 1))
            evidence = segments[index]
            db.add(QAAnswer(
                evaluation_id=evaluation.id,
                question_id=item["question_id"],
                passed=bool(item["passed"]),
                score=max(0, min(int(item["score"]), 100)),
                confidence=max(0, min(int(item["confidence"]), 100)),
                evidence_quote=evidence["text"],
                evidence_start_ms=evidence["start_ms"],
                evidence_end_ms=evidence["end_ms"],
                reasoning=item["reasoning"],
            ))

    risk = max(0, min(int(payload["predicted_dissatisfaction_risk"]), 100))
    db.add(SurveyResponse(tenant_id=conversation.tenant_id, conversation_id=conversation.id, actual_csat=None, predicted_satisfaction_risk=risk, source="predicted_groq_v1"))
    db.add(CostEvent(tenant_id=conversation.tenant_id, conversation_id=conversation.id, category="telephony", provider="asterisk_webrtc" if use_live_segments else "recording_import", units=max(recording.duration_ms // 1000, 1), unit_name="seconds", cost_micros_inr=0))
    if transcription is not None:
        db.add(CostEvent(tenant_id=conversation.tenant_id, conversation_id=conversation.id, category="transcription", provider=settings.groq_final_asr_model, units=max(recording.duration_ms // 1000, 1), unit_name="audio_seconds", cost_micros_inr=estimate_asr_cost_micros_inr(settings.groq_final_asr_model, recording.duration_ms / 1000, settings.usd_to_inr)))
    total_tokens = analysis.usage.input_tokens + analysis.usage.output_tokens
    db.add(CostEvent(tenant_id=conversation.tenant_id, conversation_id=conversation.id, category="inference", provider=settings.groq_qa_model, units=total_tokens, unit_name="tokens", cost_micros_inr=estimate_llm_cost_micros_inr(settings.groq_qa_model, analysis.usage, settings.usd_to_inr)))
    db.add(CostEvent(tenant_id=conversation.tenant_id, conversation_id=conversation.id, category="storage", provider="local_disk", units=Path(recording.storage_key).stat().st_size, unit_name="bytes", cost_micros_inr=0))
    conversation.summary = payload["summary"]
    conversation.ended_at = datetime.now(timezone.utc)
