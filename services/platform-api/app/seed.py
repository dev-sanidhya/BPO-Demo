from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AgentPresence, AgentStatus, Campaign, QueueMember, Role, Tenant, User, WorkQueue
from .security import hash_password


def seed_demo(db: Session) -> None:
    settings = get_settings()
    if not settings.seed_demo or db.scalar(select(Tenant.id).limit(1)):
        return

    tenant = Tenant(name="Aperture BPO Pilot", slug="aperture-pilot", ai_mode="local")
    db.add(tenant)
    db.flush()

    users = [
        User(tenant_id=tenant.id, email=settings.seed_admin_email.lower(), display_name="Pilot Admin", password_hash=hash_password(settings.seed_admin_password), role=Role.ADMIN),
        User(tenant_id=tenant.id, email="supervisor@pilot.example", display_name="Maya Supervisor", password_hash=hash_password(settings.seed_admin_password), role=Role.SUPERVISOR),
        User(tenant_id=tenant.id, email="agent1@pilot.example", display_name="Aarav Agent", password_hash=hash_password(settings.seed_admin_password), role=Role.AGENT),
        User(tenant_id=tenant.id, email="agent2@pilot.example", display_name="Meera Agent", password_hash=hash_password(settings.seed_admin_password), role=Role.AGENT),
        User(tenant_id=tenant.id, email="client@pilot.example", display_name="Client Viewer", password_hash=hash_password(settings.seed_admin_password), role=Role.CLIENT_VIEWER),
    ]
    db.add_all(users)
    db.flush()

    campaign = Campaign(tenant_id=tenant.id, name="Customer Care Pilot", direction="blended")
    db.add(campaign)
    db.flush()
    queue = WorkQueue(tenant_id=tenant.id, campaign_id=campaign.id, name="Pilot Support", channels=["voice", "web_chat"])
    db.add(queue)
    db.flush()

    for user in users[2:4]:
        db.add(QueueMember(queue_id=queue.id, user_id=user.id))
        db.add(AgentPresence(user_id=user.id, tenant_id=tenant.id, status=AgentStatus.OFFLINE))
    db.commit()
