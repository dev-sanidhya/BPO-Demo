from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .dependencies import current_user, require_roles
from .models import AgentPresence, AuditEvent, Conversation, ConversationStatus, Role, User
from .schemas import AssignRequest, ConversationCreate, ConversationView, LoginRequest, PresenceUpdate, PresenceView, TokenResponse, UserView
from .security import create_access_token, verify_password
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
def assign_conversation(conversation_id: str, payload: AssignRequest, user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR)), db: Session = Depends(get_db)) -> ConversationView:
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
        presence.status = "busy"
        presence.current_conversation_id = conversation.id
        presence.changed_at = datetime.now(timezone.utc)
    audit(db, user, "conversation.assigned", "conversation", conversation.id, {"assigned_user_id": assignee.id})
    db.commit()
    db.refresh(conversation)
    return ConversationView.model_validate(conversation)


@app.get("/dashboard/summary")
def dashboard_summary(user: User = Depends(require_roles(Role.ADMIN, Role.SUPERVISOR, Role.QA_REVIEWER, Role.CLIENT_VIEWER)), db: Session = Depends(get_db)) -> dict:
    counts = dict(db.execute(select(Conversation.status, func.count()).where(Conversation.tenant_id == user.tenant_id).group_by(Conversation.status)).all())
    return {"conversations": {status.value: counts.get(status, 0) for status in ConversationStatus}}

