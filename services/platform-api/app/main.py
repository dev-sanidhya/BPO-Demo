from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .dependencies import current_user, require_roles
from .models import AgentPresence, AgentStatus, AuditEvent, Channel, ChannelConfig, ChatSession, Contact, Conversation, ConversationStatus, Message, QAAnswer, QAEvaluation, QAForm, QAQuestion, QAReview, QueueMember, Role, Tenant, User
from .realtime import realtime_hub
from .schemas import AssignRequest, ChatMessageCreate, ChatStartRequest, ConversationCreate, ConversationView, LoginRequest, PresenceUpdate, PresenceView, QAEvaluationCreate, QAFormCreate, QAReviewCreate, TokenResponse, UserView, WrapUpRequest
from .security import create_access_token, decode_access_token, verify_password
from .seed import seed_demo


def audit(db: Session, user: User, action: str, entity_type: str, entity_id: str | None, details: dict | None = None) -> None:
    db.add(AuditEvent(tenant_id=user.tenant_id, actor_user_id=user.id, action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}))


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
    stmt = select(Conversation).where(Conversation.tenant_id == user.tenant_id)
    if user.role == Role.AGENT:
        stmt = stmt.where(Conversation.assigned_user_id == user.id)
    stmt = stmt.order_by(Conversation.created_at.desc()).limit(100)
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
    queues = db.scalars(select(WorkQueue).where(WorkQueue.tenant_id == user.tenant_id, WorkQueue.active.is_(True)).order_by(WorkQueue.name))
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
    return conversation


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
    contact = Contact(tenant_id=tenant.id, name=payload.customer_name, email=str(payload.customer_email) if payload.customer_email else None, language=payload.language)
    db.add(contact)
    db.flush()
    conversation = Conversation(tenant_id=tenant.id, queue_id=queue_id, contact_id=contact.id, channel=Channel.WEB_CHAT, status=ConversationStatus.QUEUED, direction="inbound", language=payload.language)
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
    counts = dict(db.execute(select(Conversation.status, func.count()).where(Conversation.tenant_id == user.tenant_id).group_by(Conversation.status)).all())
    presence_counts = dict(db.execute(select(AgentPresence.status, func.count()).where(AgentPresence.tenant_id == user.tenant_id).group_by(AgentPresence.status)).all())
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
