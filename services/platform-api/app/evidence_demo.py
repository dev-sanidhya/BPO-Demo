from __future__ import annotations

from array import array
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import wave

from sqlalchemy import select, text

from .ai import GroqAI, estimate_asr_cost_micros_inr, estimate_llm_cost_micros_inr, retrieve_knowledge
from .config import get_settings
from .database import SessionLocal
from .models import (
    AgentPresence, AgentStatus, AssistEvent, AuditEvent, Campaign, Channel, ChannelConfig,
    ClientAccessGrant, Contact, Conversation, ConversationStatus, CostEvent, KnowledgeArticle,
    Message, QAEvaluation, QAAnswer, QAForm, QAQuestion, QueueMember, Recording, Role, Script,
    SurveyResponse, Tenant, TranscriptSegment, User, VoiceSession, WorkQueue,
)
from .security import hash_password


SOURCE_URL = "https://github.com/cricketclub/gridspace-stanford-harper-valley"
PAPER_URL = "https://arxiv.org/abs/2010.13929"
SIDS = ["eb82ec7b5f0944ca", "ff0296d00e5e4184", "3a20358e1bfc4a17", "a7ccc3379af44b9f"]
QUESTION_SPECS = [
    ("11111111-1111-4111-8111-111111111111", "Professional greeting and identification", "Use the published human transcript to verify a greeting and bank/agent identification.", 20, False),
    ("22222222-2222-4222-8222-222222222222", "Understood the caller's stated task", "The response must address the task explicitly stated by the caller.", 20, False),
    ("33333333-3333-4333-8333-333333333333", "Provided an answer supported by task metadata", "The resolution must agree with the published source task metadata.", 30, True),
    ("44444444-4444-4444-8444-444444444444", "Offered further help", "Look for an explicit offer of additional assistance.", 15, False),
    ("55555555-5555-4555-8555-555555555555", "Closed the call professionally", "Look for a courteous closing from the agent.", 15, False),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_datetime(milliseconds: int) -> datetime:
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)


def confidence(segment: dict) -> int:
    return max(1, min(round(100 + float(segment["avg_logprob"]) * 20 - float(segment["no_speech_prob"]) * 40), 99))


def make_stereo(caller_path: Path, agent_path: Path, output_path: Path) -> tuple[int, int]:
    with wave.open(str(caller_path), "rb") as caller, wave.open(str(agent_path), "rb") as agent:
        if caller.getnchannels() != 1 or agent.getnchannels() != 1:
            raise ValueError("HarperValley source tracks must be mono")
        if (caller.getframerate(), caller.getsampwidth()) != (agent.getframerate(), agent.getsampwidth()) or caller.getsampwidth() != 2:
            raise ValueError("HarperValley source tracks must share 16-bit PCM parameters")
        caller_samples = array("h", caller.readframes(caller.getnframes()))
        agent_samples = array("h", agent.readframes(agent.getnframes()))
        frames = max(len(caller_samples), len(agent_samples))
        caller_samples.extend([0] * (frames - len(caller_samples)))
        agent_samples.extend([0] * (frames - len(agent_samples)))
        stereo = array("h")
        for caller_sample, agent_sample in zip(caller_samples, agent_samples):
            stereo.extend((caller_sample, agent_sample))
        with wave.open(str(output_path), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(caller.getframerate())
            output.writeframes(stereo.tobytes())
        return round(frames / caller.getframerate() * 1000), frames


def prepare_calls(source_root: Path) -> list[dict]:
    settings = get_settings()
    provider = GroqAI(settings)
    questions = [{"id": item[0], "label": item[1], "guidance": item[2], "weight": item[3], "fatal": item[4]} for item in QUESTION_SPECS]
    source_rows = []
    knowledge = []
    for sid in SIDS:
        metadata_path = source_root / "metadata" / f"{sid}.json"
        transcript_path = source_root / "transcript" / f"{sid}.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source_transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        task = metadata["tasks"][0]
        article = {"title": f"Published task metadata: {task['task_type']}", "content": f"HarperValleyBank SID {sid} source task metadata: {json.dumps(task, sort_keys=True)}", "tags": ["harpervalley", sid, *str(task["task_type"]).split()]}
        knowledge.append(article)
        source_rows.append({"sid": sid, "metadata": metadata, "source_transcript": source_transcript, "metadata_path": metadata_path, "transcript_path": transcript_path, "article": article})

    prepared = []
    with tempfile.TemporaryDirectory(prefix="aperture-evidence-") as temporary:
        temporary_root = Path(temporary)
        for row in source_rows:
            sid = row["sid"]
            caller_path = source_root / "audio" / "caller" / f"{sid}.wav"
            agent_path = source_root / "audio" / "agent" / f"{sid}.wav"
            mixed_path = temporary_root / f"{sid}.wav"
            duration_ms, _ = make_stereo(caller_path, agent_path, mixed_path)
            role_results = {
                "customer": provider.transcribe(str(caller_path), settings.groq_final_asr_model, "en"),
                "agent": provider.transcribe(str(agent_path), settings.groq_final_asr_model, "en"),
            }
            segments = []
            for role, transcription in role_results.items():
                for item in transcription.segments:
                    segments.append({**item, "speaker": role, "language": "en", "confidence": confidence(item)})
            segments.sort(key=lambda item: (item["start_ms"], item["speaker"]))
            if not segments or {item["speaker"] for item in segments} != {"agent", "customer"}:
                raise RuntimeError(f"Groq did not return both speaker tracks for {sid}")
            retrieved = retrieve_knowledge(" ".join(item["text"] for item in segments), knowledge)
            script = "Derived from published HarperValleyBank dialog patterns: greet and identify the bank, understand the caller task, ask only for task-relevant details, answer from supplied task metadata, offer further help, and close professionally."
            analysis = provider.analyze(segments, questions, script, retrieved, "en")
            prepared.append({
                **row,
                "caller_path": caller_path,
                "agent_path": agent_path,
                "mixed_bytes": mixed_path.read_bytes(),
                "duration_ms": duration_ms,
                "segments": segments,
                "role_results": role_results,
                "analysis": analysis,
                "retrieved": retrieved,
            })
            print(json.dumps({"prepared": sid, "segments": len(segments), "qa_answers": len(analysis.payload["qa_answers"]), "asr_requests": [result.request_id for result in role_results.values()], "analysis_request": analysis.request_id}), flush=True)
    return prepared


def reset_and_load(source_root: Path, prepared: list[dict]) -> dict:
    settings = get_settings()
    expected_users = {
        settings.seed_admin_email.lower(): ("Platform Administrator", Role.ADMIN),
        "supervisor@pilot.example": ("Demo Supervisor", Role.SUPERVISOR),
        "agent1@pilot.example": ("Demo Agent 01", Role.AGENT),
        "agent2@pilot.example": ("Demo Agent 02", Role.AGENT),
        "client@pilot.example": ("Demo Client Viewer", Role.CLIENT_VIEWER),
    }
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "aperture-pilot"))
        if tenant is None:
            tenant = Tenant(name="Aperture CX Evidence Demo", slug="aperture-pilot", ai_mode="external")
            db.add(tenant); db.flush()
        tenant.name = "Aperture CX Evidence Demo"; tenant.ai_mode = "external"
        db.execute(text("TRUNCATE TABLE campaigns, contacts, audit_events, durable_jobs, agent_presence, channel_configs RESTART IDENTITY CASCADE"))
        for user in list(db.scalars(select(User).where(User.tenant_id == tenant.id))):
            if user.email not in expected_users:
                db.delete(user)
        users = {}
        for email, (name, role) in expected_users.items():
            user = db.scalar(select(User).where(User.tenant_id == tenant.id, User.email == email))
            if user is None:
                user = User(tenant_id=tenant.id, email=email, display_name=name, password_hash=hash_password(settings.seed_admin_password), role=role)
                db.add(user); db.flush()
            user.display_name = name; user.role = role; user.active = True
            users[email] = user

        campaign = Campaign(tenant_id=tenant.id, name="HarperValleyBank Evidence Demo", direction="inbound")
        db.add(campaign); db.flush()
        queue = WorkQueue(tenant_id=tenant.id, campaign_id=campaign.id, name="Evidence Demo Queue", channels=["voice", "web_chat"])
        db.add(queue); db.flush()
        for email in ("agent1@pilot.example", "agent2@pilot.example"):
            db.add(QueueMember(queue_id=queue.id, user_id=users[email].id))
            db.add(AgentPresence(user_id=users[email].id, tenant_id=tenant.id, status=AgentStatus.AVAILABLE))
        db.add(ClientAccessGrant(tenant_id=tenant.id, user_id=users["client@pilot.example"].id, campaign_id=campaign.id))
        for channel in (Channel.VOICE, Channel.WEB_CHAT):
            config = ChannelConfig(tenant_id=tenant.id, channel=channel, enabled=True, settings={"queue_id": queue.id, "provider": "groq_external"} if channel == Channel.VOICE else {"queue_id": queue.id})
            if channel == Channel.WEB_CHAT:
                config.public_key_hash = hashlib.sha256(settings.seed_chat_widget_key.encode()).hexdigest()
            db.add(config)
        script = Script(tenant_id=tenant.id, campaign_id=campaign.id, name="Corpus-derived banking call flow", version=1, language="en", content="Derived from published HarperValleyBank dialog patterns: greet and identify the bank, understand the caller task, ask only for task-relevant details, answer from supplied task metadata, offer further help, and close professionally.", required_steps=[item[1] for item in QUESTION_SPECS])
        db.add(script)
        for row in prepared:
            article = row["article"]
            db.add(KnowledgeArticle(tenant_id=tenant.id, campaign_id=campaign.id, title=article["title"], language="en", content=article["content"], tags=article["tags"]))
        db.add(KnowledgeArticle(tenant_id=tenant.id, campaign_id=campaign.id, title="Evidence and licensing boundary", language="en", content="HarperValleyBank contains published human-recorded simulated banking calls under CC BY 4.0. It is not production customer traffic. Aperture transcripts, guidance, QA, summaries, costs, and stereo files are derived artifacts.", tags=["provenance", "license", "boundary"]))
        form = QAForm(tenant_id=tenant.id, campaign_id=campaign.id, name="Corpus-derived Banking QA", version=1)
        db.add(form); db.flush()
        for position, spec in enumerate(QUESTION_SPECS, 1):
            db.add(QAQuestion(id=spec[0], form_id=form.id, position=position, label=spec[1], guidance=spec[2], weight=spec[3], fatal=spec[4]))
        db.flush()

        recording_dir = Path(settings.recording_dir)
        recording_dir.mkdir(parents=True, exist_ok=True)
        imported_ids = []
        for index, row in enumerate(prepared):
            sid = row["sid"]; metadata = row["metadata"]; payload = row["analysis"].payload
            agent_user = users["agent1@pilot.example" if index % 2 == 0 else "agent2@pilot.example"]
            contact = Contact(tenant_id=tenant.id, external_ref=f"harpervalley:{sid}", name=metadata["caller"]["metadata"]["first and last name"], language="en", attributes={"evidence_class": "published_simulated_identity", "source_sid": sid})
            db.add(contact); db.flush()
            conversation = Conversation(tenant_id=tenant.id, campaign_id=campaign.id, queue_id=queue.id, contact_id=contact.id, assigned_user_id=agent_user.id, channel=Channel.VOICE, status=ConversationStatus.CLOSED, direction="inbound", external_ref=f"harpervalley:{sid}", language="en", disposition=str(metadata["tasks"][0]["task_type"]), summary=payload["summary"], started_at=source_datetime(metadata["start_time_ms"]), ended_at=source_datetime(metadata["end_time_ms"]))
            db.add(conversation); db.flush(); imported_ids.append(conversation.id)
            db.add(VoiceSession(conversation_id=conversation.id, tenant_id=tenant.id, provider="groq_external", provider_call_id=f"harper-import-{sid}", state="ended", started_at=conversation.started_at, ended_at=conversation.ended_at))
            destination = recording_dir / f"{conversation.id}.wav"; destination.write_bytes(row["mixed_bytes"])
            db.add(Recording(tenant_id=tenant.id, conversation_id=conversation.id, storage_key=str(destination), mime_type="audio/wav", duration_ms=row["duration_ms"], sha256=hashlib.sha256(row["mixed_bytes"]).hexdigest(), channels=2))
            for item in row["segments"]:
                db.add(TranscriptSegment(tenant_id=tenant.id, conversation_id=conversation.id, speaker=item["speaker"], text=item["text"], start_ms=item["start_ms"], end_ms=item["end_ms"], language="en", confidence=item["confidence"]))
            for item in payload["assists"][:3]:
                evidence = row["segments"][max(0, min(int(item["evidence_segment_index"]), len(row["segments"]) - 1))]
                db.add(AssistEvent(tenant_id=tenant.id, conversation_id=conversation.id, event_type=item["event_type"], title=item["title"][:160], content=item["content"], evidence_start_ms=evidence["start_ms"], evidence_end_ms=evidence["end_ms"], metadata_json={"source": "groq_post_call", "model": settings.groq_qa_model, "request_id": row["analysis"].request_id, "retrieved_articles": [article["title"] for article in row["retrieved"]]}))
            answers = payload["qa_answers"]; by_id = {spec[0]: spec for spec in QUESTION_SPECS}
            if {item["question_id"] for item in answers} != set(by_id):
                raise RuntimeError(f"Groq QA did not cover the evidence rubric for {sid}")
            total_weight = sum(spec[3] for spec in QUESTION_SPECS)
            score = round(sum(max(0, min(int(item["score"]), 100)) * by_id[item["question_id"]][3] for item in answers) / total_weight)
            evaluation = QAEvaluation(tenant_id=tenant.id, conversation_id=conversation.id, form_id=form.id, automatic_score=score, fatal_triggered=any(not item["passed"] and by_id[item["question_id"]][4] for item in answers), provider="groq", model=settings.groq_qa_model, rubric_version=form.version, summary=payload["summary"])
            db.add(evaluation); db.flush()
            for item in answers:
                evidence = row["segments"][max(0, min(int(item["evidence_segment_index"]), len(row["segments"]) - 1))]
                db.add(QAAnswer(evaluation_id=evaluation.id, question_id=item["question_id"], passed=bool(item["passed"]), score=max(0, min(int(item["score"]), 100)), confidence=max(0, min(int(item["confidence"]), 100)), evidence_quote=evidence["text"], evidence_start_ms=evidence["start_ms"], evidence_end_ms=evidence["end_ms"], reasoning=item["reasoning"]))
            risk = max(0, min(int(payload["predicted_dissatisfaction_risk"]), 100))
            db.add(SurveyResponse(tenant_id=tenant.id, conversation_id=conversation.id, actual_csat=None, predicted_satisfaction_risk=risk, source="predicted_groq_v1"))
            audio_seconds = sum(result.duration_seconds for result in row["role_results"].values())
            db.add(CostEvent(tenant_id=tenant.id, conversation_id=conversation.id, category="telephony", provider="licensed_dataset_import", units=max(row["duration_ms"] // 1000, 1), unit_name="seconds", cost_micros_inr=0))
            db.add(CostEvent(tenant_id=tenant.id, conversation_id=conversation.id, category="transcription", provider=settings.groq_final_asr_model, units=max(round(audio_seconds), 1), unit_name="audio_seconds", cost_micros_inr=estimate_asr_cost_micros_inr(settings.groq_final_asr_model, audio_seconds, settings.usd_to_inr)))
            usage = row["analysis"].usage
            db.add(CostEvent(tenant_id=tenant.id, conversation_id=conversation.id, category="inference", provider=settings.groq_qa_model, units=usage.input_tokens + usage.output_tokens, unit_name="tokens", cost_micros_inr=estimate_llm_cost_micros_inr(settings.groq_qa_model, usage, settings.usd_to_inr)))
            db.add(CostEvent(tenant_id=tenant.id, conversation_id=conversation.id, category="storage", provider="local_disk", units=len(row["mixed_bytes"]), unit_name="bytes", cost_micros_inr=0))
            db.add(AuditEvent(tenant_id=tenant.id, actor_user_id=users[settings.seed_admin_email.lower()].id, action="evidence.provenance_recorded", entity_type="conversation", entity_id=conversation.id, details={
                "classification": "published_human_recorded_simulated_call", "label": "Published human-recorded simulated call", "source_name": "Stanford/Gridspace HarperValleyBank", "source_url": SOURCE_URL, "paper_url": PAPER_URL, "license": "CC BY 4.0", "source_id": sid,
                "boundary": "Human speakers performed a simulated banking call for a published research corpus. This is not production customer traffic. Transcript, guidance, QA, summary, predicted risk, costs, and stereo recording are Aperture-derived.",
                "transformations": ["Original caller and agent mono tracks transcribed separately by Groq whisper-large-v3", "Original tracks interleaved as caller-left and agent-right stereo without speech synthesis", "Groq openai/gpt-oss-20b generated guidance, QA, summary, and predicted risk from the derived transcript"],
                "source_hashes": {"caller_audio_sha256": sha256(row["caller_path"]), "agent_audio_sha256": sha256(row["agent_path"]), "metadata_sha256": sha256(row["metadata_path"]), "transcript_sha256": sha256(row["transcript_path"])},
                "published_scores": {"caller_partner_rating_10pt": metadata["caller"]["survey_response"]["data"].get("partner_rating"), "script": metadata["labels"].get("lhvb_script"), "caller_mos": metadata["labels"].get("caller_mos"), "agent_mos": metadata["labels"].get("agent_mos")},
                "rating_boundary": "Published partner_rating is retained as source metadata and is not stored or reported as CSAT.",
            }))

        # A clearly labelled channel replay proves the unified digital timeline without claiming native chat provenance.
        replay = prepared[1]; sid = replay["sid"]; metadata = replay["metadata"]
        contact = Contact(tenant_id=tenant.id, external_ref=f"harpervalley-chat-replay:{sid}", name=metadata["caller"]["metadata"]["first and last name"], language="en", attributes={"evidence_class": "published_call_transcript_replay"})
        db.add(contact); db.flush()
        chat = Conversation(tenant_id=tenant.id, campaign_id=campaign.id, queue_id=queue.id, contact_id=contact.id, assigned_user_id=users["agent1@pilot.example"].id, channel=Channel.WEB_CHAT, status=ConversationStatus.CLOSED, direction="inbound", external_ref=f"harpervalley-chat-replay:{sid}", language="en", disposition="source_transcript_replay", summary="Published human call transcript replayed as a digital timeline to exercise the unified channel view; not a native historical chat.", started_at=source_datetime(metadata["start_time_ms"]), ended_at=source_datetime(metadata["end_time_ms"]))
        db.add(chat); db.flush(); imported_ids.append(chat.id)
        for sequence, turn in enumerate(replay["source_transcript"], 1):
            db.add(Message(conversation_id=chat.id, sender_type="customer" if turn["speaker_role"] == "caller" else "agent", sender_user_id=users["agent1@pilot.example"].id if turn["speaker_role"] == "agent" else None, content=turn["human_transcript"], sequence=sequence, metadata_json={"source_sid": sid, "source_turn_index": turn["index"]}, created_at=source_datetime(turn["start_timestamp_ms"])))
        db.add(AuditEvent(tenant_id=tenant.id, actor_user_id=users[settings.seed_admin_email.lower()].id, action="evidence.provenance_recorded", entity_type="conversation", entity_id=chat.id, details={"classification": "published_call_transcript_channel_replay", "label": "Published transcript channel replay", "source_name": "Stanford/Gridspace HarperValleyBank", "source_url": SOURCE_URL, "paper_url": PAPER_URL, "license": "CC BY 4.0", "source_id": sid, "boundary": "Exact human-transcript turns from a published simulated voice call were mapped into web-chat messages. This proves the product's unified digital workflow but is not evidence of a native historical chat.", "transformations": ["Caller role mapped to customer", "Agent role mapped to agent", "Human transcript text preserved"], "source_hashes": {"transcript_sha256": sha256(replay["transcript_path"])}}))
        db.commit()
        return {"tenant_id": tenant.id, "campaign_id": campaign.id, "conversation_ids": imported_ids, "voice_calls": len(prepared), "channel_replays": 1}


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace fixture-heavy pilot data with licensed, provenance-backed evidence.")
    parser.add_argument("source_root", type=Path)
    args = parser.parse_args()
    if not (args.source_root / "manifest.json").is_file():
        raise SystemExit(f"HarperValley evidence manifest not found under {args.source_root}")
    prepared = prepare_calls(args.source_root)
    print(json.dumps(reset_and_load(args.source_root, prepared), indent=2), flush=True)


if __name__ == "__main__":
    main()
