from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
import hashlib

from .models import AgentPresence, AgentStatus, Campaign, Channel, ChannelConfig, QueueMember, Role, Tenant, User, WorkQueue
from .security import hash_password


def seed_demo(db: Session) -> None:
    settings = get_settings()
    if not settings.seed_demo:
        return

    tenant = db.scalar(select(Tenant).where(Tenant.slug == "aperture-pilot"))
    if tenant is None:
        tenant = Tenant(name="Aperture BPO Pilot", slug="aperture-pilot", ai_mode="local")
        db.add(tenant)
        db.flush()

    user_specs = [
        (settings.seed_admin_email.lower(), "Pilot Admin", Role.ADMIN),
        ("supervisor@pilot.example", "Maya Supervisor", Role.SUPERVISOR),
        ("agent1@pilot.example", "Aarav Agent", Role.AGENT),
        ("agent2@pilot.example", "Meera Agent", Role.AGENT),
        ("client@pilot.example", "Client Viewer", Role.CLIENT_VIEWER),
    ]
    users: list[User] = []
    for email, display_name, role in user_specs:
        user = db.scalar(select(User).where(User.tenant_id == tenant.id, User.email == email))
        if user is None:
            user = User(tenant_id=tenant.id, email=email, display_name=display_name, password_hash=hash_password(settings.seed_admin_password), role=role)
            db.add(user)
            db.flush()
        users.append(user)

    campaign = db.scalar(select(Campaign).where(Campaign.tenant_id == tenant.id, Campaign.name == "Customer Care Pilot"))
    if campaign is None:
        campaign = Campaign(tenant_id=tenant.id, name="Customer Care Pilot", direction="blended")
        db.add(campaign)
        db.flush()
    queue = db.scalar(select(WorkQueue).where(WorkQueue.tenant_id == tenant.id, WorkQueue.name == "Pilot Support"))
    if queue is None:
        queue = WorkQueue(tenant_id=tenant.id, campaign_id=campaign.id, name="Pilot Support", channels=["voice", "web_chat"])
        db.add(queue)
        db.flush()

    for user in users[2:4]:
        if db.scalar(select(QueueMember.id).where(QueueMember.queue_id == queue.id, QueueMember.user_id == user.id)) is None:
            db.add(QueueMember(queue_id=queue.id, user_id=user.id))
        if db.get(AgentPresence, user.id) is None:
            db.add(AgentPresence(user_id=user.id, tenant_id=tenant.id, status=AgentStatus.OFFLINE))
    chat_config = db.scalar(select(ChannelConfig).where(ChannelConfig.tenant_id == tenant.id, ChannelConfig.channel == Channel.WEB_CHAT))
    if chat_config is None:
        chat_config = ChannelConfig(tenant_id=tenant.id, channel=Channel.WEB_CHAT)
        db.add(chat_config)
    chat_config.enabled = True
    chat_config.public_key_hash = hashlib.sha256(settings.seed_chat_widget_key.encode()).hexdigest()
    chat_config.settings = {"queue_id": queue.id}
    db.commit()
