from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .dependencies import current_user, require_roles
from .models import AgentPresence, AuditEvent, Conversation, ConversationStatus, QAAnswer, QAEvaluation, QAForm, QAQuestion, QAReview, Role, User
from .schemas import AssignRequest, ConversationCreate, ConversationView, LoginRequest, PresenceUpdate, PresenceView, QAEvaluationCreate, QAFormCreate, QAReviewCreate, TokenResponse, UserView
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
