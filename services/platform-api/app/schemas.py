from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import AgentStatus, Channel, ConversationStatus, Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    email: str
    display_name: str
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class PresenceUpdate(BaseModel):
    status: AgentStatus
    reason: str | None = Field(default=None, max_length=160)


class PresenceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    tenant_id: str
    status: AgentStatus
    reason: str | None
    current_conversation_id: str | None
    changed_at: datetime


class ConversationCreate(BaseModel):
    channel: Channel
    direction: str = Field(pattern="^(inbound|outbound)$")
    campaign_id: str | None = None
    queue_id: str | None = None
    contact_id: str | None = None
    language: str = Field(default="en", max_length=20)


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    campaign_id: str | None
    queue_id: str | None
    contact_id: str | None
    assigned_user_id: str | None
    channel: Channel
    status: ConversationStatus
    direction: str
    language: str
    disposition: str | None
    summary: str | None
    started_at: datetime
    ended_at: datetime | None


class AssignRequest(BaseModel):
    user_id: str


class WrapUpRequest(BaseModel):
    disposition: str = Field(min_length=2, max_length=120)
    summary: str = Field(min_length=2, max_length=5000)


class VoiceDialRequest(BaseModel):
    phone: str = Field(min_length=3, max_length=40)
    customer_name: str = Field(default="Voice customer", min_length=1, max_length=160)
    language: str = Field(default="en", pattern="^(en|hi|mr|hi-en|auto)$")


class VoiceControlRequest(BaseModel):
    action: str = Field(pattern="^(mute|unmute|hold|resume|transfer|hangup)$")
    target: str | None = Field(default=None, max_length=160)


class PrivacyModeUpdate(BaseModel):
    ai_mode: str = Field(pattern="^(local|external)$")


class PilotSetupUpdate(BaseModel):
    campaign_name: str = Field(min_length=3, max_length=160)
    queue_name: str = Field(min_length=3, max_length=160)
    script_content: str = Field(min_length=20, max_length=10000)
    required_steps: list[str] = Field(min_length=1, max_length=20)
    knowledge_title: str = Field(min_length=3, max_length=240)
    knowledge_content: str = Field(min_length=20, max_length=10000)
    qa_form_name: str = Field(min_length=3, max_length=160)


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=160)
    role: Role
    password: str = Field(min_length=12, max_length=128)


class QAQuestionCreate(BaseModel):
    label: str = Field(min_length=3, max_length=300)
    guidance: str = ""
    weight: int = Field(default=1, ge=1, le=100)
    fatal: bool = False


class QAFormCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    campaign_id: str | None = None
    questions: list[QAQuestionCreate] = Field(min_length=1)


class QAAnswerCreate(BaseModel):
    question_id: str
    passed: bool
    score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    evidence_quote: str = Field(min_length=1)
    evidence_start_ms: int = Field(ge=0)
    evidence_end_ms: int = Field(ge=0)
    reasoning: str = ""


class QAEvaluationCreate(BaseModel):
    form_id: str
    automatic_score: int = Field(ge=0, le=100)
    fatal_triggered: bool = False
    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=120)
    summary: str = ""
    answers: list[QAAnswerCreate] = Field(min_length=1)


class QAReviewCreate(BaseModel):
    reviewed_score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=5, max_length=2000)
    fatal_resolution: Literal["confirmed", "cleared"] | None = None


class CoachingActionCreate(BaseModel):
    evaluation_id: str
    focus: str = Field(min_length=3, max_length=300)
    action_plan: str = Field(min_length=5, max_length=3000)
    due_at: datetime | None = None


class ChatStartRequest(BaseModel):
    tenant_slug: str = Field(min_length=2, max_length=80)
    widget_key: str = Field(min_length=8, max_length=200)
    customer_name: str = Field(min_length=1, max_length=160)
    customer_email: EmailStr | None = None
    language: str = Field(default="en", max_length=20)
    initial_message: str = Field(min_length=1, max_length=5000)


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class SurveySubmit(BaseModel):
    csat: int = Field(ge=1, le=5)
