from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import io
from pathlib import Path
import secrets
import shutil
import wave

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .ai import AIProviderError, GroqAI, estimate_asr_cost_micros_inr, estimate_llm_cost_micros_inr, retrieve_knowledge
from .database import Base, SessionLocal, engine, get_db
from .dependencies import current_user, require_roles
from .jobs import start_voice_finalization
from .models import AgentPresence, AgentStatus, AssistEvent, AuditEvent, Campaign, Channel, ChannelConfig, ChatSession, ClientAccessGrant, Contact, Conversation, ConversationStatus, CostEvent, DurableJob, JobStatus, KnowledgeArticle, Message, QAAnswer, QAEvaluation, QAForm, QAQuestion, QAReview, QueueMember, Recording, Role, Script, SurveyResponse, Tenant, TranscriptSegment, User, VoiceSession, WorkQueue
from .realtime import realtime_hub
from .reporting import simple_pdf
from .schemas import AssignRequest, ChatMessageCreate, ChatStartRequest, ConversationCreate, ConversationView, LoginRequest, PilotSetupUpdate, PresenceUpdate, PresenceView, PrivacyModeUpdate, QAEvaluationCreate, QAFormCreate, QAReviewCreate, SurveySubmit, TokenResponse, UserCreate, UserView, VoiceControlRequest, VoiceDialRequest, WrapUpRequest
from .security import create_access_token, decode_access_token, hash_password, verify_password
from .seed import seed_demo


def audit(db: Session, user: User, action: str, entity_type: str, entity_id: str | None, details: dict | None = None) -> None:
    db.add(AuditEvent(tenant_id=user.tenant_id, actor_user_id=user.id, action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}))


def scoped_conversation_stmt(user: User):
    stmt = select(Conversation).where(Conversation.tenant_id == user.tenant_id)
    if user.role == Role.AGENT:
        stmt = stmt.where(Conversation.assigned_user_id == user.id)
    elif user.role == Role.CLIENT_VIEWER:
        campaign_ids = select(ClientAccessGrant.campaign_id).where(ClientAccessGrant.user_id == user.id, ClientAccessGrant.tenant_id == user.tenant_id)
        stmt = stmt.where(Conversation.campaign_id.in_(campaign_ids))
    return stmt


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo(db)
    yield


app = FastAPI(title="Unified BPO AI Platform API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Chat-Session"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token(user.id, user.tenant_id, user.role.value)
    audit(db, user, "auth.login", "user", user.id)
    db.commit()
    return TokenResponse(access_token=token, user=UserView.model_validate(user))


@app.get("/me", response_model=UserView)
def me(user: User = Depends(current_user)) -> UserView:
    return UserView.model_validate(user)


@app.put("/agents/me/presence", response_model=PresenceView)
def update_presence(payload: PresenceUpdate, user: User = Depends(require_roles(Role.AGENT)), db: Session = Depends(get_db)) -> PresenceView:
    presence = db.get(AgentPresence, user.id)
    if presence is None:
        presence = AgentPresence(user_id=user.id, tenant_id=user.tenant_id)
        db.add(presence)
    presence.status = payload.status
    presence.reason = payload.reason
    presence.changed_at = datetime.now(timezone.utc)
    audit(db, user, "agent.presence_changed", "user", user.id, {"status": payload.status.value, "reason": payload.reason})
    db.commit()
    db.refresh(presence)
    return PresenceView.model_validate(presence)


@app.get("/conversations", response_model=list[ConversationView])
def list_conversations(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[ConversationView]:
    stmt = scoped_conversation_stmt(user).order_by(Conversation.created_at.desc()).limit(100)
    return [ConversationView.model_validate(row) for row in db.scalars(stmt)]


@app.get("/work/queued", response_model=list[ConversationView])
def queued_work(user: User = Depends(require_roles(Role.AGENT)), db: Session = Depends(get_db)) -> list[ConversationView]:
    queue_ids = select(QueueMember.queue_id).where(QueueMember.user_id == user.id)
    stmt = select(Conversation).where(
        Conversation.tenant_id == user.tenant_id,
        Conversation.queue_id.in_(queue_ids),
        Conversation.status == ConversationStatus.QUEUED,
        Conversation.assigned_user_id.is_(None),
    ).order_by(Conversation.created_at).limit(100)
    return [ConversationView.model_validate(row) for row in db.scalars(stmt)]


@app.get("/queues")
def list_queues(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    from .models import WorkQueue
    stmt = select(WorkQueue).where(WorkQueue.tenant_id == user.tenant_id, WorkQueue.active.is_(True))
    if user.role == Role.CLIENT_VIEWER:
        campaign_ids = select(ClientAccessGrant.campaign_id).where(ClientAccessGrant.user_id == user.id, ClientAccessGrant.tenant_id == user.tenant_id)
        stmt = stmt.where(WorkQueue.campaign_id.in_(campaign_ids))
    queues = db.scalars(stmt.order_by(WorkQueue.name))
    return [{"id": queue.id, "name": queue.name, "campaign_id": queue.campaign_id, "channels": queue.channels} for queue in queues]


@app.get("/agents")
def list_agents(user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR, Role.QA_REVIEWER)), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(User, AgentPresence)
        .outerjoin(AgentPresence, AgentPresence.user_id == User.id)
        .where(User.tenant_id == user.tenant_id, User.role == Role.AGENT, User.active.is_(True))
        .order_by(User.display_name)
    )
    return [{"id": agent.id, "display_name": agent.display_name, "email": agent.email, "status": presence.status.value if presence else "offline", "current_conversation_id": presence.current_conversation_id if presence else None} for agent, presence in rows]


@app.post("/conversations", response_model=ConversationView, status_code=201)
def create_conversation(payload: ConversationCreate, user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR)), db: Session = Depends(get_db)) -> ConversationView:
    conversation = Conversation(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(conversation)
    db.flush()
    audit(db, user, "conversation.created", "conversation", conversation.id, {"channel": payload.channel.value})
    db.commit()
    db.refresh(conversation)
    return ConversationView.model_validate(conversation)


@app.post("/conversations/{conversation_id}/assign", response_model=ConversationView)
async def assign_conversation(conversation_id: str, payload: AssignRequest, user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR)), db: Session = Depends(get_db)) -> ConversationView:
    conversation = db.get(Conversation, conversation_id)
    assignee = db.get(User, payload.user_id)
    if conversation is None or conversation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if assignee is None or assignee.tenant_id != user.tenant_id or assignee.role != Role.AGENT:
        raise HTTPException(status_code=400, detail="Assignee must be an active agent in this tenant")
    conversation.assigned_user_id = assignee.id
    conversation.status = ConversationStatus.ACTIVE
    presence = db.get(AgentPresence, assignee.id)
    if presence:
        presence.status = AgentStatus.BUSY
        presence.current_conversation_id = conversation.id
        presence.changed_at = datetime.now(timezone.utc)
    audit(db, user, "conversation.assigned", "conversation", conversation.id, {"assigned_user_id": assignee.id})
    db.commit()
    db.refresh(conversation)
    await realtime_hub.publish(user.tenant_id, {"type": "conversation.assigned", "conversation_id": conversation.id, "assigned_user_id": assignee.id}, assignee.id)
    return ConversationView.model_validate(conversation)


@app.post("/conversations/{conversation_id}/claim", response_model=ConversationView)
async def claim_conversation(conversation_id: str, user: User = Depends(require_roles(Role.AGENT)), db: Session = Depends(get_db)) -> ConversationView:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id).with_for_update())
    if conversation is None or conversation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.status != ConversationStatus.QUEUED or conversation.assigned_user_id is not None:
        raise HTTPException(status_code=409, detail="Conversation is no longer available")
    if conversation.queue_id and db.scalar(select(QueueMember.id).where(QueueMember.queue_id == conversation.queue_id, QueueMember.user_id == user.id)) is None:
        raise HTTPException(status_code=403, detail="Agent is not a member of this queue")
    conversation.assigned_user_id = user.id
    conversation.status = ConversationStatus.ACTIVE
    voice_session = db.get(VoiceSession, conversation.id) if conversation.channel == Channel.VOICE else None
    if voice_session:
        voice_session.state = "active"
    presence = db.get(AgentPresence, user.id)
    if presence:
        presence.status = AgentStatus.BUSY
        presence.current_conversation_id = conversation.id
        presence.changed_at = datetime.now(timezone.utc)
    audit(db, user, "conversation.claimed", "conversation", conversation.id)
    db.commit()
    db.refresh(conversation)
    await realtime_hub.publish(user.tenant_id, {"type": "conversation.claimed", "conversation_id": conversation.id, "assigned_user_id": user.id}, user.id)
    return ConversationView.model_validate(conversation)


@app.post("/conversations/{conversation_id}/wrap-up", response_model=ConversationView)
async def wrap_up_conversation(conversation_id: str, payload: WrapUpRequest, user: User = Depends(require_roles(Role.AGENT, Role.SUPERVISOR, Role.ADMIN)), db: Session = Depends(get_db)) -> ConversationView:
    conversation = _authorized_conversation(db, user, conversation_id)
    if conversation.status not in {ConversationStatus.ACTIVE, ConversationStatus.WRAP_UP}:
        raise HTTPException(status_code=409, detail="Conversation is not available for wrap-up")
    conversation.status = ConversationStatus.CLOSED
    conversation.disposition = payload.disposition
    conversation.summary = payload.summary
    conversation.ended_at = datetime.now(timezone.utc)
    if conversation.assigned_user_id:
        presence = db.get(AgentPresence, conversation.assigned_user_id)
        if presence:
            presence.status = AgentStatus.WRAP_UP
            presence.current_conversation_id = None
            presence.changed_at = datetime.now(timezone.utc)
    audit(db, user, "conversation.wrapped_up", "conversation", conversation.id, {"disposition": payload.disposition})
    db.commit()
    db.refresh(conversation)
    await realtime_hub.publish(user.tenant_id, {"type": "conversation.closed", "conversation_id": conversation.id, "disposition": conversation.disposition}, conversation.assigned_user_id)
    return ConversationView.model_validate(conversation)


def _message_view(message: Message) -> dict:
    return {"id": message.id, "conversation_id": message.conversation_id, "sender_type": message.sender_type, "sender_user_id": message.sender_user_id, "content": message.content, "sequence": message.sequence, "created_at": message.created_at.isoformat()}


def _authorized_conversation(db: Session, user: User, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if user.role == Role.AGENT and conversation.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Conversation is not assigned to this agent")
    if user.role == Role.CLIENT_VIEWER:
        grant = db.scalar(select(ClientAccessGrant.id).where(ClientAccessGrant.user_id == user.id, ClientAccessGrant.campaign_id == conversation.campaign_id))
        if grant is None:
            raise HTTPException(status_code=403, detail="Conversation is outside the client's authorized scope")
    return conversation


def _voice_view(session: VoiceSession) -> dict:
    return {"conversation_id": session.conversation_id, "provider": session.provider, "provider_call_id": session.provider_call_id, "state": session.state, "muted": session.muted, "held": session.held, "transfer_target": session.transfer_target, "started_at": session.started_at.isoformat(), "ended_at": session.ended_at.isoformat() if session.ended_at else None}


@app.post("/voice/calls/dial", status_code=201)
async def dial_voice(payload: VoiceDialRequest, user: User = Depends(require_roles(Role.AGENT)), db: Session = Depends(get_db)) -> dict:
    active = db.scalar(select(Conversation.id).where(Conversation.assigned_user_id == user.id, Conversation.status == ConversationStatus.ACTIVE))
    if active:
        raise HTTPException(status_code=409, detail="Agent already has an active interaction")
    config = db.scalar(select(ChannelConfig).where(ChannelConfig.tenant_id == user.tenant_id, ChannelConfig.channel == Channel.VOICE, ChannelConfig.enabled.is_(True)))
    if config is None:
        raise HTTPException(status_code=409, detail="Voice channel is not configured")
    queue = db.get(WorkQueue, config.settings.get("queue_id"))
    if queue is None:
        raise HTTPException(status_code=409, detail="Voice queue is not configured")
    contact = Contact(tenant_id=user.tenant_id, name=payload.customer_name, phone=payload.phone, language=payload.language)
    db.add(contact)
    db.flush()
    conversation = Conversation(tenant_id=user.tenant_id, campaign_id=queue.campaign_id, queue_id=queue.id, contact_id=contact.id, assigned_user_id=user.id, channel=Channel.VOICE, status=ConversationStatus.ACTIVE, direction="outbound", language=payload.language)
    db.add(conversation)
    db.flush()
    tenant = db.get(Tenant, user.tenant_id)
    provider = "groq_external" if tenant and tenant.ai_mode == "external" else "deterministic_local"
    session = VoiceSession(conversation_id=conversation.id, tenant_id=user.tenant_id, provider=provider, provider_call_id=f"{provider}-{conversation.id}")
    db.add(session)
    db.add(AssistEvent(tenant_id=user.tenant_id, conversation_id=conversation.id, event_type="script", title="Opening", content="Greet the customer and state your name before discussing the order.", metadata_json={"source": "Customer Care Core v1"}))
    presence = db.get(AgentPresence, user.id)
    if presence:
        presence.status = AgentStatus.BUSY
        presence.current_conversation_id = conversation.id
        presence.changed_at = datetime.now(timezone.utc)
    audit(db, user, "voice.dialed", "conversation", conversation.id, {"provider": session.provider, "language": payload.language})
    db.commit()
    await realtime_hub.publish(user.tenant_id, {"type": "voice.started", "conversation_id": conversation.id}, user.id)
    return {"conversation": ConversationView.model_validate(conversation), "session": _voice_view(session)}


@app.put("/voice/calls/{conversation_id}/recording")
def upload_voice_recording(
    conversation_id: str,
    recording_file: UploadFile = File(alias="file"),
    duration_ms: int | None = Form(default=None, ge=1),
    user: User = Depends(require_roles(Role.AGENT)),
    db: Session = Depends(get_db),
) -> dict:
    conversation = _authorized_conversation(db, user, conversation_id)
    session = db.get(VoiceSession, conversation.id)
    if conversation.channel != Channel.VOICE or session is None or session.state not in {"active", "held"}:
        raise HTTPException(status_code=409, detail="A recording can only be attached to an active voice call")
    if db.scalar(select(Recording.id).where(Recording.conversation_id == conversation.id)):
        raise HTTPException(status_code=409, detail="This call already has a recording")
    suffix = Path(recording_file.filename or "").suffix.lower()
    if suffix not in {".wav", ".webm", ".ogg", ".mp3", ".m4a"}:
        raise HTTPException(status_code=415, detail="Recording must be WAV, WebM, OGG, MP3, or M4A")
    destination = Path(settings.recording_dir) / f"{conversation.id}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        shutil.copyfileobj(recording_file.file, output)
    channels = 1
    if suffix == ".wav":
        try:
            with wave.open(str(destination), "rb") as audio:
                duration_ms = round(audio.getnframes() / audio.getframerate() * 1000)
                channels = audio.getnchannels()
        except (wave.Error, EOFError) as error:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="The uploaded file is not a readable WAV recording") from error
    elif duration_ms is None:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="duration_ms is required for compressed browser recordings")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    mime_type = recording_file.content_type or {".webm": "audio/webm", ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}.get(suffix, "audio/wav")
    db.add(Recording(tenant_id=user.tenant_id, conversation_id=conversation.id, storage_key=str(destination), mime_type=mime_type, duration_ms=duration_ms, sha256=digest, channels=channels))
    audit(db, user, "voice.recording_attached", "conversation", conversation.id, {"duration_ms": duration_ms, "channels": channels, "sha256": digest})
    db.commit()
    return {"conversation_id": conversation.id, "duration_ms": duration_ms, "channels": channels, "sha256": digest, "mime_type": mime_type}


@app.post("/voice/calls/{conversation_id}/audio-chunks", status_code=201)
async def ingest_voice_chunk(
    conversation_id: str,
    audio_file: UploadFile = File(alias="file"),
    speaker: str = Form(pattern="^(agent|customer|unknown)$"),
    start_ms: int = Form(ge=0),
    user: User = Depends(require_roles(Role.AGENT)),
    db: Session = Depends(get_db),
) -> dict:
    conversation = _authorized_conversation(db, user, conversation_id)
    tenant = db.get(Tenant, user.tenant_id)
    session = db.get(VoiceSession, conversation.id)
    if tenant is None or tenant.ai_mode != "external":
        raise HTTPException(status_code=409, detail="Near-real-time cloud guidance requires external AI mode")
    if conversation.channel != Channel.VOICE or session is None or session.state not in {"active", "held"}:
        raise HTTPException(status_code=409, detail="Audio chunks require an active voice call")
    if not (audio_file.filename or "").lower().endswith((".wav", ".webm", ".ogg", ".mp3", ".m4a")):
        raise HTTPException(status_code=415, detail="Unsupported audio chunk format")
    suffix = Path(audio_file.filename or "chunk.webm").suffix.lower()
    chunk_dir = Path(settings.recording_dir) / ".chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunk_dir / f"{conversation.id}-{secrets.token_hex(8)}{suffix}"
    try:
        with chunk_path.open("wb") as output:
            shutil.copyfileobj(audio_file.file, output)
        provider = GroqAI(settings)
        result = provider.transcribe(str(chunk_path), settings.groq_realtime_asr_model, conversation.language)
    finally:
        chunk_path.unlink(missing_ok=True)
    created_segments: list[dict] = []
    for item in result.segments:
        row = TranscriptSegment(
            tenant_id=user.tenant_id,
            conversation_id=conversation.id,
            speaker=speaker,
            text=item["text"],
            start_ms=start_ms + item["start_ms"],
            end_ms=start_ms + item["end_ms"],
            language=conversation.language if conversation.language != "auto" else result.language,
            confidence=max(1, min(round(100 + item["avg_logprob"] * 20 - item["no_speech_prob"] * 40), 99)),
        )
        db.add(row)
        db.flush()
        created_segments.append({"id": row.id, "speaker": row.speaker, "text": row.text, "start_ms": row.start_ms, "end_ms": row.end_ms, "language": row.language, "confidence": row.confidence})
    all_rows = list(db.scalars(select(TranscriptSegment).where(TranscriptSegment.conversation_id == conversation.id).order_by(TranscriptSegment.start_ms)))
    transcript = [{"speaker": row.speaker, "text": row.text, "start_ms": row.start_ms, "end_ms": row.end_ms} for row in all_rows]
    db.add(CostEvent(tenant_id=user.tenant_id, conversation_id=conversation.id, category="transcription", provider=settings.groq_realtime_asr_model, units=max(round(result.duration_seconds), 1), unit_name="audio_seconds", cost_micros_inr=estimate_asr_cost_micros_inr(settings.groq_realtime_asr_model, result.duration_seconds, settings.usd_to_inr)))
    if not transcript:
        audit(db, user, "voice.chunk_transcribed", "conversation", conversation.id, {"speaker": speaker, "start_ms": start_ms, "segments": 0, "asr_request_id": result.request_id})
        db.commit()
        return {"segments": [], "assists": [], "detected_language": result.language}
    script = db.scalar(select(Script).where(Script.tenant_id == user.tenant_id, Script.active.is_(True)).order_by(Script.version.desc()))
    articles = list(db.scalars(select(KnowledgeArticle).where(KnowledgeArticle.tenant_id == user.tenant_id, KnowledgeArticle.active.is_(True))))
    article_payload = [{"title": item.title, "content": item.content, "tags": item.tags} for item in articles]
    retrieved = retrieve_knowledge(" ".join(row["text"] for row in transcript), article_payload)
    try:
        analysis = provider.analyze(transcript, [], script.content if script else "Use professional customer-service practices.", retrieved, conversation.language, live=True)
    except AIProviderError as error:
        message = str(error)
        audit(db, user, "voice.live_guidance_failed", "conversation", conversation.id, {"speaker": speaker, "start_ms": start_ms, "asr_request_id": result.request_id, "error": message[:500]})
        db.commit()
        await realtime_hub.publish(user.tenant_id, {"type": "assist.failed", "conversation_id": conversation.id, "detail": message}, user.id)
        return {"segments": created_segments, "assists": [], "detected_language": result.language, "guidance_error": message}
    assists: list[dict] = []
    for item in analysis.payload["assists"][:3]:
        index = max(0, min(int(item["evidence_segment_index"]), len(transcript) - 1))
        evidence = transcript[index]
        event = AssistEvent(tenant_id=user.tenant_id, conversation_id=conversation.id, event_type=item["event_type"], title=item["title"][:160], content=item["content"], evidence_start_ms=evidence["start_ms"], evidence_end_ms=evidence["end_ms"], metadata_json={"source": "groq_live", "model": settings.groq_guidance_model, "request_id": analysis.request_id, "retrieved_articles": [article["title"] for article in retrieved]})
        db.add(event)
        db.flush()
        assists.append({"id": event.id, "event_type": event.event_type, "title": event.title, "content": event.content, "evidence_start_ms": event.evidence_start_ms, "evidence_end_ms": event.evidence_end_ms, "metadata": event.metadata_json})
    usage_tokens = analysis.usage.input_tokens + analysis.usage.output_tokens
    db.add(CostEvent(tenant_id=user.tenant_id, conversation_id=conversation.id, category="inference", provider=settings.groq_guidance_model, units=usage_tokens, unit_name="tokens", cost_micros_inr=estimate_llm_cost_micros_inr(settings.groq_guidance_model, analysis.usage, settings.usd_to_inr)))
    audit(db, user, "voice.chunk_analyzed", "conversation", conversation.id, {"speaker": speaker, "start_ms": start_ms, "segments": len(created_segments), "asr_request_id": result.request_id, "analysis_request_id": analysis.request_id})
    db.commit()
    await realtime_hub.publish(user.tenant_id, {"type": "assist.generated", "conversation_id": conversation.id, "assists": assists}, user.id)
    return {"segments": created_segments, "assists": assists, "detected_language": analysis.payload["detected_language"]}


@app.post("/voice/calls/simulate-inbound", status_code=201)
async def simulate_inbound_voice(payload: VoiceDialRequest, user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR)), db: Session = Depends(get_db)) -> dict:
    config = db.scalar(select(ChannelConfig).where(ChannelConfig.tenant_id == user.tenant_id, ChannelConfig.channel == Channel.VOICE, ChannelConfig.enabled.is_(True)))
    queue = db.get(WorkQueue, config.settings.get("queue_id")) if config else None
    if queue is None:
        raise HTTPException(status_code=409, detail="Voice queue is not configured")
    contact = Contact(tenant_id=user.tenant_id, name=payload.customer_name, phone=payload.phone, language=payload.language)
    db.add(contact)
    db.flush()
    conversation = Conversation(tenant_id=user.tenant_id, campaign_id=queue.campaign_id, queue_id=queue.id, contact_id=contact.id, channel=Channel.VOICE, status=ConversationStatus.QUEUED, direction="inbound", language=payload.language)
    db.add(conversation)
    db.flush()
    session = VoiceSession(conversation_id=conversation.id, tenant_id=user.tenant_id, provider_call_id=f"local-inbound-{conversation.id}", state="ringing")
    db.add(session)
    audit(db, user, "voice.inbound_simulated", "conversation", conversation.id)
    db.commit()
    await realtime_hub.publish(user.tenant_id, {"type": "conversation.queued", "conversation_id": conversation.id, "channel": "voice"})
    return {"conversation": ConversationView.model_validate(conversation), "session": _voice_view(session)}


@app.post("/voice/calls/register-live-inbound", status_code=201)
async def register_live_inbound_voice(payload: VoiceDialRequest, user: User = Depends(require_roles(Role.AGENT)), db: Session = Depends(get_db)) -> dict:
    active = db.scalar(select(Conversation.id).where(Conversation.assigned_user_id == user.id, Conversation.status == ConversationStatus.ACTIVE))
    if active:
        raise HTTPException(status_code=409, detail="Agent already has an active interaction")
    config = db.scalar(select(ChannelConfig).where(ChannelConfig.tenant_id == user.tenant_id, ChannelConfig.channel == Channel.VOICE, ChannelConfig.enabled.is_(True)))
    queue = db.get(WorkQueue, config.settings.get("queue_id")) if config else None
    if queue is None:
        raise HTTPException(status_code=409, detail="Voice queue is not configured")
    tenant = db.get(Tenant, user.tenant_id)
    provider = "groq_external" if tenant and tenant.ai_mode == "external" else "deterministic_local"
    contact = Contact(tenant_id=user.tenant_id, name=payload.customer_name, phone=payload.phone, language=payload.language)
    db.add(contact)
    db.flush()
    conversation = Conversation(tenant_id=user.tenant_id, campaign_id=queue.campaign_id, queue_id=queue.id, contact_id=contact.id, channel=Channel.VOICE, status=ConversationStatus.QUEUED, direction="inbound", language=payload.language)
    db.add(conversation)
    db.flush()
    session = VoiceSession(conversation_id=conversation.id, tenant_id=user.tenant_id, provider=provider, provider_call_id=f"sip-inbound-{conversation.id}", state="ringing")
    db.add(session)
    audit(db, user, "voice.inbound_registered", "conversation", conversation.id, {"provider": provider, "source": "asterisk_webrtc"})
    db.commit()
    await realtime_hub.publish(user.tenant_id, {"type": "conversation.queued", "conversation_id": conversation.id, "channel": "voice"}, user.id)
    return {"conversation": ConversationView.model_validate(conversation), "session": _voice_view(session)}


@app.post("/voice/calls/{conversation_id}/reject")
async def reject_inbound_voice(conversation_id: str, user: User = Depends(require_roles(Role.AGENT)), db: Session = Depends(get_db)) -> dict:
    conversation = db.get(Conversation, conversation_id)
    session = db.get(VoiceSession, conversation_id)
    if conversation is None or session is None or conversation.tenant_id != user.tenant_id or conversation.status != ConversationStatus.QUEUED:
        raise HTTPException(status_code=409, detail="Inbound call is no longer ringing")
    if conversation.queue_id and db.scalar(select(QueueMember.id).where(QueueMember.queue_id == conversation.queue_id, QueueMember.user_id == user.id)) is None:
        raise HTTPException(status_code=403, detail="Agent is not a member of this queue")
    conversation.status = ConversationStatus.FAILED
    conversation.ended_at = datetime.now(timezone.utc)
    conversation.disposition = "rejected"
    session.state = "rejected"
    session.ended_at = conversation.ended_at
    audit(db, user, "voice.rejected", "conversation", conversation.id)
    db.commit()
    await realtime_hub.publish(user.tenant_id, {"type": "voice.rejected", "conversation_id": conversation.id})
    return _voice_view(session)


@app.get("/voice/calls/{conversation_id}")
def get_voice_call(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    conversation = _authorized_conversation(db, user, conversation_id)
    session = db.get(VoiceSession, conversation.id)
    if conversation.channel != Channel.VOICE or session is None:
        raise HTTPException(status_code=404, detail="Voice call not found")
    session_view = _voice_view(session)
    session_view["recording_available"] = db.scalar(select(Recording.id).where(Recording.conversation_id == conversation.id)) is not None
    return {"conversation": ConversationView.model_validate(conversation), "session": session_view}


@app.post("/voice/calls/{conversation_id}/control")
async def control_voice(conversation_id: str, payload: VoiceControlRequest, user: User = Depends(require_roles(Role.AGENT)), db: Session = Depends(get_db)) -> dict:
    conversation = _authorized_conversation(db, user, conversation_id)
    session = db.get(VoiceSession, conversation.id)
    if conversation.channel != Channel.VOICE or session is None:
        raise HTTPException(status_code=404, detail="Voice call not found")
    if session.state not in {"active", "held"}:
        raise HTTPException(status_code=409, detail="Voice call has already ended")
    if payload.action == "mute":
        session.muted = True
    elif payload.action == "unmute":
        session.muted = False
    elif payload.action == "hold":
        session.held = True
        session.state = "held"
    elif payload.action == "resume":
        session.held = False
        session.state = "active"
    elif payload.action == "transfer":
        if not payload.target:
            raise HTTPException(status_code=400, detail="Transfer target is required")
        session.transfer_target = payload.target
    if payload.action == "hangup":
        session.state = "ended"
        session.ended_at = datetime.now(timezone.utc)
        conversation.status = ConversationStatus.WRAP_UP
        presence = db.get(AgentPresence, user.id)
        if presence:
            presence.status = AgentStatus.WRAP_UP
            presence.current_conversation_id = conversation.id
            presence.changed_at = datetime.now(timezone.utc)
    audit(db, user, f"voice.{payload.action}", "conversation", conversation.id, {"target": payload.target})
    if payload.action == "hangup":
        # Media teardown must never wait on transcription or QA. A single durable
        # worker claims this job and retries provider failures independently.
        start_voice_finalization(db, conversation)
    else:
        db.commit()
    db.refresh(session)
    await realtime_hub.publish(user.tenant_id, {"type": f"voice.{payload.action}", "conversation_id": conversation.id, "session": _voice_view(session)}, user.id)
    return _voice_view(session)


@app.get("/conversations/{conversation_id}/transcript")
def conversation_transcript(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    _authorized_conversation(db, user, conversation_id)
    segments = db.scalars(select(TranscriptSegment).where(TranscriptSegment.conversation_id == conversation_id).order_by(TranscriptSegment.start_ms))
    return [{"id": segment.id, "speaker": segment.speaker, "text": segment.text, "start_ms": segment.start_ms, "end_ms": segment.end_ms, "language": segment.language, "confidence": segment.confidence} for segment in segments]


@app.get("/conversations/{conversation_id}/assist")
def conversation_assist(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    _authorized_conversation(db, user, conversation_id)
    events = db.scalars(select(AssistEvent).where(AssistEvent.conversation_id == conversation_id).order_by(AssistEvent.created_at))
    return [{"id": event.id, "event_type": event.event_type, "title": event.title, "content": event.content, "evidence_start_ms": event.evidence_start_ms, "evidence_end_ms": event.evidence_end_ms, "metadata": event.metadata_json} for event in events]


@app.get("/conversations/{conversation_id}/evidence")
def conversation_evidence(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    conversation = _authorized_conversation(db, user, conversation_id)
    provenance = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == user.tenant_id, AuditEvent.entity_type == "conversation", AuditEvent.entity_id == conversation.id, AuditEvent.action == "evidence.provenance_recorded")
        .order_by(AuditEvent.created_at.desc())
    )
    if provenance:
        return {"conversation_id": conversation.id, **provenance.details, "recorded_at": provenance.created_at.isoformat()}
    session = db.get(VoiceSession, conversation.id) if conversation.channel == Channel.VOICE else None
    live_sip = bool(session and session.provider_call_id.startswith("sip-"))
    return {
        "conversation_id": conversation.id,
        "classification": "live_platform_interaction" if live_sip else "unattributed_interaction",
        "label": "Live platform capture" if live_sip else "Source attribution not attached",
        "source_name": None,
        "source_url": None,
        "license": None,
        "source_id": None,
        "transformations": [],
        "boundary": "This record has no external dataset attribution. Verify the participant and capture context before using it as demo evidence.",
        "recorded_at": None,
    }


@app.get("/conversations/{conversation_id}/recording")
def conversation_recording(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    _authorized_conversation(db, user, conversation_id)
    recording = db.scalar(select(Recording).where(Recording.conversation_id == conversation_id))
    if recording is None or not Path(recording.storage_key).is_file():
        raise HTTPException(status_code=404, detail="Recording not found")
    return FileResponse(recording.storage_key, media_type=recording.mime_type, filename=f"{conversation_id}{Path(recording.storage_key).suffix}", headers={"Accept-Ranges": "bytes"})


@app.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    _authorized_conversation(db, user, conversation_id)
    return [_message_view(message) for message in db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.sequence))]


@app.post("/conversations/{conversation_id}/messages", status_code=201)
async def send_agent_message(conversation_id: str, payload: ChatMessageCreate, user: User = Depends(require_roles(Role.AGENT, Role.SUPERVISOR, Role.ADMIN)), db: Session = Depends(get_db)) -> dict:
    conversation = _authorized_conversation(db, user, conversation_id)
    if conversation.channel != Channel.WEB_CHAT or conversation.status != ConversationStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Conversation is not an active web chat")
    sequence = (db.scalar(select(func.max(Message.sequence)).where(Message.conversation_id == conversation.id)) or 0) + 1
    message = Message(conversation_id=conversation.id, sender_type="agent", sender_user_id=user.id, content=payload.content, sequence=sequence)
    db.add(message)
    audit(db, user, "chat.message_sent", "conversation", conversation.id, {"sequence": sequence})
    db.commit()
    db.refresh(message)
    event = {"type": "chat.message", "conversation_id": conversation.id, "message": _message_view(message)}
    await realtime_hub.publish(user.tenant_id, event, conversation.assigned_user_id)
    return _message_view(message)


def _valid_chat_session(db: Session, conversation_id: str, token: str) -> ChatSession:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = db.scalar(select(ChatSession).where(ChatSession.conversation_id == conversation_id, ChatSession.token_hash == token_hash))
    now = datetime.now(timezone.utc)
    if session is None or session.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=401, detail="Invalid or expired chat session")
    return session


@app.post("/public/chat/start", status_code=201)
async def start_public_chat(payload: ChatStartRequest, db: Session = Depends(get_db)) -> dict:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == payload.tenant_slug, Tenant.active.is_(True)))
    if tenant is None:
        raise HTTPException(status_code=404, detail="Chat widget not found")
    config = db.scalar(select(ChannelConfig).where(ChannelConfig.tenant_id == tenant.id, ChannelConfig.channel == Channel.WEB_CHAT, ChannelConfig.enabled.is_(True)))
    if config is None or not secrets.compare_digest(config.public_key_hash or "", hashlib.sha256(payload.widget_key.encode()).hexdigest()):
        raise HTTPException(status_code=404, detail="Chat widget not found")
    queue_id = config.settings.get("queue_id")
    queue = db.get(WorkQueue, queue_id)
    if queue is None:
        raise HTTPException(status_code=503, detail="Chat queue is unavailable")
    contact = Contact(tenant_id=tenant.id, name=payload.customer_name, email=str(payload.customer_email) if payload.customer_email else None, language=payload.language)
    db.add(contact)
    db.flush()
    conversation = Conversation(tenant_id=tenant.id, campaign_id=queue.campaign_id, queue_id=queue_id, contact_id=contact.id, channel=Channel.WEB_CHAT, status=ConversationStatus.QUEUED, direction="inbound", language=payload.language)
    db.add(conversation)
    db.flush()
    message = Message(conversation_id=conversation.id, sender_type="customer", content=payload.initial_message, sequence=1)
    session_token = secrets.token_urlsafe(32)
    db.add(message)
    db.add(ChatSession(tenant_id=tenant.id, conversation_id=conversation.id, token_hash=hashlib.sha256(session_token.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(hours=24)))
    db.commit()
    await realtime_hub.publish(tenant.id, {"type": "conversation.queued", "conversation_id": conversation.id, "channel": "web_chat"})
    return {"conversation_id": conversation.id, "session_token": session_token, "status": conversation.status.value}


@app.get("/public/chat/{conversation_id}/messages")
def list_customer_messages(conversation_id: str, x_chat_session: str = Header(alias="X-Chat-Session"), db: Session = Depends(get_db)) -> list[dict]:
    _valid_chat_session(db, conversation_id, x_chat_session)
    return [_message_view(message) for message in db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.sequence))]


@app.post("/public/chat/{conversation_id}/messages", status_code=201)
async def send_customer_message(conversation_id: str, payload: ChatMessageCreate, x_chat_session: str = Header(alias="X-Chat-Session"), db: Session = Depends(get_db)) -> dict:
    session = _valid_chat_session(db, conversation_id, x_chat_session)
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.status not in {ConversationStatus.QUEUED, ConversationStatus.ACTIVE}:
        raise HTTPException(status_code=409, detail="Chat is closed")
    sequence = (db.scalar(select(func.max(Message.sequence)).where(Message.conversation_id == conversation.id)) or 0) + 1
    message = Message(conversation_id=conversation.id, sender_type="customer", content=payload.content, sequence=sequence)
    db.add(message)
    db.commit()
    db.refresh(message)
    event = {"type": "chat.message", "conversation_id": conversation.id, "message": _message_view(message)}
    await realtime_hub.publish(session.tenant_id, event, conversation.assigned_user_id)
    return _message_view(message)


@app.get("/public/chat/{conversation_id}/status")
def public_chat_status(conversation_id: str, x_chat_session: str = Header(alias="X-Chat-Session"), db: Session = Depends(get_db)) -> dict:
    _valid_chat_session(db, conversation_id, x_chat_session)
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.channel != Channel.WEB_CHAT:
        raise HTTPException(status_code=404, detail="Chat not found")
    survey = db.scalar(select(SurveyResponse).where(SurveyResponse.conversation_id == conversation.id))
    return {"status": conversation.status.value, "actual_csat": survey.actual_csat if survey else None}


@app.post("/public/chat/{conversation_id}/survey", status_code=201)
def submit_chat_survey(conversation_id: str, payload: SurveySubmit, x_chat_session: str = Header(alias="X-Chat-Session"), db: Session = Depends(get_db)) -> dict:
    session = _valid_chat_session(db, conversation_id, x_chat_session)
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.status != ConversationStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Survey is available after the conversation closes")
    survey = db.scalar(select(SurveyResponse).where(SurveyResponse.conversation_id == conversation.id))
    if survey is None:
        survey = SurveyResponse(tenant_id=session.tenant_id, conversation_id=conversation.id, source="customer_widget")
        db.add(survey)
    survey.actual_csat = payload.csat
    survey.source = "customer_widget"
    survey.received_at = datetime.now(timezone.utc)
    db.commit()
    return {"actual_csat": survey.actual_csat, "source": survey.source}


@app.websocket("/realtime")
async def realtime_events(websocket: WebSocket) -> None:
    protocols = [value.strip() for value in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    if len(protocols) != 2 or protocols[0] != "bpo-realtime":
        await websocket.close(code=4401)
        return
    try:
        payload = decode_access_token(protocols[1])
        with SessionLocal() as db:
            user = db.get(User, payload.get("sub"))
            if user is None or not user.active or user.tenant_id != payload.get("tenant_id"):
                raise ValueError("invalid user")
            db.expunge(user)
    except Exception:
        await websocket.close(code=4401)
        return
    await websocket.accept(subprotocol="bpo-realtime")
    await realtime_hub.connect(user, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await realtime_hub.disconnect(user.id, websocket)


@app.get("/dashboard/summary")
def dashboard_summary(user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR, Role.QA_REVIEWER, Role.CLIENT_VIEWER)), db: Session = Depends(get_db)) -> dict:
    scoped = scoped_conversation_stmt(user).subquery()
    counts = dict(db.execute(select(scoped.c.status, func.count()).group_by(scoped.c.status)).all())
    presence_counts = {} if user.role == Role.CLIENT_VIEWER else dict(db.execute(select(AgentPresence.status, func.count()).where(AgentPresence.tenant_id == user.tenant_id).group_by(AgentPresence.status)).all())
    return {
        "conversations": {conversation_status.value: counts.get(conversation_status, 0) for conversation_status in ConversationStatus},
        "agents": {agent_status.value: presence_counts.get(agent_status, 0) for agent_status in AgentStatus},
    }


@app.post("/qa/forms", status_code=201)
def create_qa_form(payload: QAFormCreate, user: User = Depends(require_roles(Role.ADMIN, Role.QA_REVIEWER)), db: Session = Depends(get_db)) -> dict:
    form = QAForm(tenant_id=user.tenant_id, campaign_id=payload.campaign_id, name=payload.name, version=1)
    db.add(form)
    db.flush()
    for position, question in enumerate(payload.questions, start=1):
        db.add(QAQuestion(form_id=form.id, position=position, **question.model_dump()))
    audit(db, user, "qa_form.created", "qa_form", form.id, {"question_count": len(payload.questions)})
    db.commit()
    return {"id": form.id, "name": form.name, "version": form.version}


@app.post("/conversations/{conversation_id}/qa/evaluations", status_code=201)
def create_qa_evaluation(conversation_id: str, payload: QAEvaluationCreate, user: User = Depends(require_roles(Role.ADMIN, Role.QA_REVIEWER, Role.SUPERVISOR)), db: Session = Depends(get_db)) -> dict:
    conversation = db.get(Conversation, conversation_id)
    form = db.get(QAForm, payload.form_id)
    if conversation is None or conversation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if form is None or form.tenant_id != user.tenant_id:
        raise HTTPException(status_code=400, detail="QA form not found")
    question_ids = set(db.scalars(select(QAQuestion.id).where(QAQuestion.form_id == form.id)))
    answer_ids = {answer.question_id for answer in payload.answers}
    if answer_ids != question_ids:
        raise HTTPException(status_code=400, detail="Evaluation must answer every form question exactly once")
    for answer in payload.answers:
        if answer.evidence_end_ms < answer.evidence_start_ms:
            raise HTTPException(status_code=400, detail="Evidence end must be after evidence start")
    evaluation = QAEvaluation(
        tenant_id=user.tenant_id,
        conversation_id=conversation.id,
        form_id=form.id,
        automatic_score=payload.automatic_score,
        fatal_triggered=payload.fatal_triggered,
        provider=payload.provider,
        model=payload.model,
        rubric_version=form.version,
        summary=payload.summary,
    )
    db.add(evaluation)
    db.flush()
    db.add_all([QAAnswer(evaluation_id=evaluation.id, **answer.model_dump()) for answer in payload.answers])
    audit(db, user, "qa_evaluation.created", "qa_evaluation", evaluation.id, {"conversation_id": conversation.id, "score": payload.automatic_score})
    db.commit()
    return {"id": evaluation.id, "automatic_score": evaluation.automatic_score, "reviewed_score": None, "status": evaluation.status}


@app.post("/qa/evaluations/{evaluation_id}/reviews", status_code=201)
def review_qa_evaluation(evaluation_id: str, payload: QAReviewCreate, user: User = Depends(require_roles(Role.ADMIN, Role.QA_REVIEWER, Role.SUPERVISOR)), db: Session = Depends(get_db)) -> dict:
    evaluation = db.get(QAEvaluation, evaluation_id)
    if evaluation is None or evaluation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="QA evaluation not found")
    previous_score = evaluation.reviewed_score if evaluation.reviewed_score is not None else evaluation.automatic_score
    review = QAReview(evaluation_id=evaluation.id, reviewer_user_id=user.id, previous_score=previous_score, reviewed_score=payload.reviewed_score, reason=payload.reason)
    db.add(review)
    evaluation.reviewed_score = payload.reviewed_score
    evaluation.status = "reviewed"
    audit(db, user, "qa_evaluation.reviewed", "qa_evaluation", evaluation.id, {"previous_score": previous_score, "reviewed_score": payload.reviewed_score, "reason": payload.reason})
    db.commit()
    return {"id": review.id, "automatic_score": evaluation.automatic_score, "reviewed_score": evaluation.reviewed_score, "status": evaluation.status}


@app.get("/qa/evaluations")
def list_qa_evaluations(user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR, Role.QA_REVIEWER, Role.CLIENT_VIEWER)), db: Session = Depends(get_db)) -> list[dict]:
    scoped = scoped_conversation_stmt(user).subquery()
    evaluations = db.scalars(select(QAEvaluation).join(scoped, scoped.c.id == QAEvaluation.conversation_id).order_by(QAEvaluation.created_at.desc()).limit(100))
    return [{"id": evaluation.id, "conversation_id": evaluation.conversation_id, "automatic_score": evaluation.automatic_score, "reviewed_score": evaluation.reviewed_score, "effective_score": evaluation.reviewed_score if evaluation.reviewed_score is not None else evaluation.automatic_score, "fatal_triggered": evaluation.fatal_triggered, "status": evaluation.status, "provider": evaluation.provider, "model": evaluation.model, "summary": evaluation.summary, "created_at": evaluation.created_at.isoformat()} for evaluation in evaluations]


@app.get("/qa/evaluations/{evaluation_id}")
def qa_evaluation_detail(evaluation_id: str, user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR, Role.QA_REVIEWER, Role.CLIENT_VIEWER)), db: Session = Depends(get_db)) -> dict:
    evaluation = db.get(QAEvaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="QA evaluation not found")
    _authorized_conversation(db, user, evaluation.conversation_id)
    answers = db.execute(select(QAAnswer, QAQuestion).join(QAQuestion, QAQuestion.id == QAAnswer.question_id).where(QAAnswer.evaluation_id == evaluation.id).order_by(QAQuestion.position)).all()
    reviews = db.scalars(select(QAReview).where(QAReview.evaluation_id == evaluation.id).order_by(QAReview.created_at))
    return {
        "id": evaluation.id,
        "conversation_id": evaluation.conversation_id,
        "automatic_score": evaluation.automatic_score,
        "reviewed_score": evaluation.reviewed_score,
        "status": evaluation.status,
        "summary": evaluation.summary,
        "answers": [{"id": answer.id, "question": question.label, "passed": answer.passed, "score": answer.score, "confidence": answer.confidence, "evidence_quote": answer.evidence_quote, "evidence_start_ms": answer.evidence_start_ms, "evidence_end_ms": answer.evidence_end_ms, "reasoning": answer.reasoning} for answer, question in answers],
        "reviews": [{"id": review.id, "previous_score": review.previous_score, "reviewed_score": review.reviewed_score, "reason": review.reason, "created_at": review.created_at.isoformat()} for review in reviews],
    }


@app.get("/configuration")
def configuration(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    tenant = db.get(Tenant, user.tenant_id)
    campaign_stmt = select(Campaign).where(Campaign.tenant_id == user.tenant_id)
    queue_stmt = select(WorkQueue).where(WorkQueue.tenant_id == user.tenant_id)
    script_stmt = select(Script).where(Script.tenant_id == user.tenant_id, Script.active.is_(True))
    article_stmt = select(KnowledgeArticle).where(KnowledgeArticle.tenant_id == user.tenant_id, KnowledgeArticle.active.is_(True))
    form_stmt = select(QAForm).where(QAForm.tenant_id == user.tenant_id, QAForm.active.is_(True))
    if user.role == Role.CLIENT_VIEWER:
        campaign_ids = select(ClientAccessGrant.campaign_id).where(ClientAccessGrant.user_id == user.id, ClientAccessGrant.tenant_id == user.tenant_id)
        campaign_stmt = campaign_stmt.where(Campaign.id.in_(campaign_ids))
        queue_stmt = queue_stmt.where(WorkQueue.campaign_id.in_(campaign_ids))
        script_stmt = script_stmt.where(Script.campaign_id.in_(campaign_ids))
        article_stmt = article_stmt.where(KnowledgeArticle.campaign_id.in_(campaign_ids))
        form_stmt = form_stmt.where(QAForm.campaign_id.in_(campaign_ids))
    campaigns = db.scalars(campaign_stmt.order_by(Campaign.name))
    queues = db.scalars(queue_stmt.order_by(WorkQueue.name))
    scripts = db.scalars(script_stmt.order_by(Script.name))
    articles = db.scalars(article_stmt.order_by(KnowledgeArticle.title))
    forms = db.scalars(form_stmt.order_by(QAForm.name))
    users = list(db.scalars(select(User).where(User.tenant_id == user.tenant_id).order_by(User.display_name))) if user.role == Role.ADMIN else []
    return {"tenant": {"id": tenant.id, "name": tenant.name, "ai_mode": tenant.ai_mode}, "campaigns": [{"id": item.id, "name": item.name, "direction": item.direction} for item in campaigns], "queues": [{"id": item.id, "name": item.name, "campaign_id": item.campaign_id, "channels": item.channels} for item in queues], "scripts": [{"id": item.id, "name": item.name, "version": item.version, "language": item.language, "content": item.content, "required_steps": item.required_steps} for item in scripts], "knowledge": [{"id": item.id, "title": item.title, "language": item.language, "content": item.content, "tags": item.tags} for item in articles], "qa_forms": [{"id": item.id, "name": item.name, "version": item.version, "campaign_id": item.campaign_id} for item in forms], "users": [{"id": item.id, "email": item.email, "display_name": item.display_name, "role": item.role.value, "active": item.active} for item in users]}


@app.put("/configuration/pilot")
def update_pilot_configuration(payload: PilotSetupUpdate, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)) -> dict:
    campaign = db.scalar(select(Campaign).where(Campaign.tenant_id == user.tenant_id, Campaign.active.is_(True)).order_by(Campaign.created_at))
    queue = db.scalar(select(WorkQueue).where(WorkQueue.tenant_id == user.tenant_id, WorkQueue.active.is_(True)).order_by(WorkQueue.name))
    script = db.scalar(select(Script).where(Script.tenant_id == user.tenant_id, Script.active.is_(True)).order_by(Script.created_at))
    article = db.scalar(select(KnowledgeArticle).where(KnowledgeArticle.tenant_id == user.tenant_id, KnowledgeArticle.active.is_(True)).order_by(KnowledgeArticle.created_at))
    form = db.scalar(select(QAForm).where(QAForm.tenant_id == user.tenant_id, QAForm.active.is_(True)).order_by(QAForm.created_at))
    if not all([campaign, queue, script, article, form]):
        raise HTTPException(status_code=409, detail="Pilot seed configuration is incomplete")
    campaign.name = payload.campaign_name
    queue.name = payload.queue_name
    script.content = payload.script_content
    script.required_steps = payload.required_steps
    article.title = payload.knowledge_title
    article.content = payload.knowledge_content
    form.name = payload.qa_form_name
    audit(db, user, "configuration.pilot_updated", "campaign", campaign.id, {"queue_id": queue.id, "script_id": script.id, "knowledge_id": article.id, "qa_form_id": form.id})
    db.commit()
    return {"status": "saved"}


@app.post("/users", response_model=UserView, status_code=201)
def create_user(payload: UserCreate, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)) -> UserView:
    if db.scalar(select(User.id).where(User.tenant_id == user.tenant_id, func.lower(User.email) == str(payload.email).lower())):
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    created = User(tenant_id=user.tenant_id, email=str(payload.email).lower(), display_name=payload.display_name, password_hash=hash_password(payload.password), role=payload.role)
    db.add(created)
    db.flush()
    if created.role == Role.AGENT:
        queue = db.scalar(select(WorkQueue).where(WorkQueue.tenant_id == user.tenant_id, WorkQueue.active.is_(True)).order_by(WorkQueue.name))
        if queue:
            db.add(QueueMember(queue_id=queue.id, user_id=created.id))
        db.add(AgentPresence(user_id=created.id, tenant_id=user.tenant_id, status=AgentStatus.OFFLINE))
    elif created.role == Role.CLIENT_VIEWER:
        campaign = db.scalar(select(Campaign).where(Campaign.tenant_id == user.tenant_id, Campaign.active.is_(True)).order_by(Campaign.created_at))
        if campaign:
            db.add(ClientAccessGrant(tenant_id=user.tenant_id, user_id=created.id, campaign_id=campaign.id))
    audit(db, user, "user.created", "user", created.id, {"role": created.role.value})
    db.commit()
    db.refresh(created)
    return UserView.model_validate(created)


@app.put("/configuration/privacy")
def update_privacy(payload: PrivacyModeUpdate, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)) -> dict:
    tenant = db.get(Tenant, user.tenant_id)
    if payload.ai_mode == "external" and not settings.groq_api_key:
        raise HTTPException(status_code=409, detail="External AI is not ready: GROQ_API_KEY is not configured on the platform server")
    tenant.ai_mode = payload.ai_mode
    audit(db, user, "privacy.mode_changed", "tenant", tenant.id, {"ai_mode": payload.ai_mode})
    db.commit()
    return {"ai_mode": tenant.ai_mode}


@app.get("/diagnostics")
def diagnostics(user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR)), db: Session = Depends(get_db)) -> dict:
    tenant = db.get(Tenant, user.tenant_id)
    oldest = db.scalar(select(func.min(Conversation.created_at)).where(Conversation.tenant_id == user.tenant_id, Conversation.status == ConversationStatus.QUEUED))
    lag = max(int((datetime.now(timezone.utc) - oldest.replace(tzinfo=timezone.utc)).total_seconds()), 0) if oldest else 0
    recording_dir = Path(settings.recording_dir)
    recording_bytes = sum(item.stat().st_size for item in recording_dir.glob("*.wav")) if recording_dir.exists() else 0
    channels = db.scalars(select(ChannelConfig).where(ChannelConfig.tenant_id == user.tenant_id))
    jobs = dict(db.execute(select(DurableJob.status, func.count()).where(DurableJob.tenant_id == user.tenant_id).group_by(DurableJob.status)).all())
    external_ready = bool(settings.groq_api_key)
    provider = "local_rules" if tenant.ai_mode == "local" else ("groq" if external_ready else "external_config_required")
    return {"status": "ok", "database": "connected", "privacy": {"mode": tenant.ai_mode, "customer_content_egress": tenant.ai_mode != "local", "provider": provider, "external_ready": external_ready, "data_retention": "Groq project policy; enable Zero Data Retention before client data" if tenant.ai_mode == "external" else "deployment-local"}, "ai": {"realtime_asr_model": settings.groq_realtime_asr_model if external_ready else None, "final_asr_model": settings.groq_final_asr_model if external_ready else None, "guidance_model": settings.groq_guidance_model if external_ready else None, "qa_model": settings.groq_qa_model if external_ready else None, "cost_fx_usd_to_inr": settings.usd_to_inr}, "queue": {"oldest_wait_seconds": lag}, "jobs": {status.value: count for status, count in jobs.items()}, "storage": {"recording_bytes": recording_bytes, "path": settings.recording_dir}, "channels": {item.channel.value: {"enabled": item.enabled, "provider": item.settings.get("provider", "internal")} for item in channels}}


def _report_conversations(db: Session, user: User, channel: Channel | None, campaign_id: str | None, queue_id: str | None, agent_id: str | None) -> list[Conversation]:
    stmt = scoped_conversation_stmt(user)
    if channel:
        stmt = stmt.where(Conversation.channel == channel)
    if campaign_id:
        stmt = stmt.where(Conversation.campaign_id == campaign_id)
    if queue_id:
        stmt = stmt.where(Conversation.queue_id == queue_id)
    if agent_id:
        stmt = stmt.where(Conversation.assigned_user_id == agent_id)
    return list(db.scalars(stmt.order_by(Conversation.started_at.desc()).limit(1000)))


@app.get("/reports/summary")
def report_summary(channel: Channel | None = None, campaign_id: str | None = None, queue_id: str | None = None, agent_id: str | None = None, user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR, Role.QA_REVIEWER, Role.CLIENT_VIEWER)), db: Session = Depends(get_db)) -> dict:
    rows = _report_conversations(db, user, channel, campaign_id, queue_id, agent_id)
    ids = [row.id for row in rows]
    evaluations = list(db.scalars(select(QAEvaluation).where(QAEvaluation.conversation_id.in_(ids)))) if ids else []
    actual_surveys = list(db.scalars(select(SurveyResponse).where(SurveyResponse.conversation_id.in_(ids), SurveyResponse.actual_csat.is_not(None)))) if ids else []
    predicted = list(db.scalars(select(SurveyResponse).where(SurveyResponse.conversation_id.in_(ids), SurveyResponse.predicted_satisfaction_risk.is_not(None)))) if ids else []
    return {"filters": {"channel": channel.value if channel else None, "campaign_id": campaign_id, "queue_id": queue_id, "agent_id": agent_id}, "conversation_count": len(rows), "closed_count": sum(row.status == ConversationStatus.CLOSED for row in rows), "average_qa": round(sum((item.reviewed_score if item.reviewed_score is not None else item.automatic_score) for item in evaluations) / len(evaluations), 1) if evaluations else None, "actual_csat_count": len(actual_surveys), "average_actual_csat": round(sum(item.actual_csat for item in actual_surveys if item.actual_csat) / len(actual_surveys), 1) if actual_surveys else None, "predicted_risk_count": len(predicted), "average_predicted_risk": round(sum(item.predicted_satisfaction_risk for item in predicted if item.predicted_satisfaction_risk is not None) / len(predicted), 1) if predicted else None}


@app.get("/reports/export.csv")
def export_csv(channel: Channel | None = None, campaign_id: str | None = None, queue_id: str | None = None, agent_id: str | None = None, user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR, Role.QA_REVIEWER, Role.CLIENT_VIEWER)), db: Session = Depends(get_db)) -> Response:
    rows = _report_conversations(db, user, channel, campaign_id, queue_id, agent_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["conversation_id", "channel", "direction", "language", "status", "agent_id", "started_at", "ended_at", "disposition"])
    for row in rows:
        writer.writerow([row.id, row.channel.value, row.direction, row.language, row.status.value, row.assigned_user_id or "", row.started_at.isoformat(), row.ended_at.isoformat() if row.ended_at else "", row.disposition or ""])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=aperture-cx-report.csv"})


@app.get("/reports/export.pdf")
def export_pdf(channel: Channel | None = None, campaign_id: str | None = None, queue_id: str | None = None, agent_id: str | None = None, user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR, Role.QA_REVIEWER, Role.CLIENT_VIEWER)), db: Session = Depends(get_db)) -> Response:
    rows = _report_conversations(db, user, channel, campaign_id, queue_id, agent_id)
    lines = [f"Generated: {datetime.now(timezone.utc).isoformat()}", f"Conversations: {len(rows)}", ""]
    lines.extend(f"{row.started_at:%Y-%m-%d %H:%M} | {row.channel.value} | {row.language} | {row.status.value} | {row.disposition or '-'}" for row in rows)
    return Response(simple_pdf("Aperture CX Client Report", lines), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=aperture-cx-report.pdf"})


@app.get("/reports/costs")
def report_costs(user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR, Role.CLIENT_VIEWER)), db: Session = Depends(get_db)) -> dict:
    scoped = scoped_conversation_stmt(user).subquery()
    rows = db.execute(select(CostEvent.category, CostEvent.provider, func.sum(CostEvent.units), CostEvent.unit_name, func.sum(CostEvent.cost_micros_inr)).join(scoped, scoped.c.id == CostEvent.conversation_id).group_by(CostEvent.category, CostEvent.provider, CostEvent.unit_name)).all()
    return {"currency": "INR", "items": [{"category": category, "provider": provider, "units": units, "unit_name": unit_name, "cost_micros_inr": cost} for category, provider, units, unit_name, cost in rows], "total_cost_micros_inr": sum(row[4] for row in rows)}
