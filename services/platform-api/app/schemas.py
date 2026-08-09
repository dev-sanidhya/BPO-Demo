from datetime import datetime

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

