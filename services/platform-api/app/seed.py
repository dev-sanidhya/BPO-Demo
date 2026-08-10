from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
import hashlib

from .models import AgentPresence, AgentStatus, Campaign, Channel, ChannelConfig, ClientAccessGrant, KnowledgeArticle, QAForm, QAQuestion, QueueMember, Role, Script, Tenant, User, WorkQueue
from .security import hash_password


def seed_demo(db: Session) -> None:
    settings = get_settings()
    if not settings.seed_demo:
        return

    tenant = db.scalar(select(Tenant).where(Tenant.slug == "aperture-pilot"))
    if tenant is None:
        tenant = Tenant(name="Aperture CX Evidence Demo", slug="aperture-pilot", ai_mode=settings.default_ai_mode)
        db.add(tenant)
        db.flush()

    user_specs = [
        (settings.seed_admin_email.lower(), "Platform Administrator", Role.ADMIN),
        ("supervisor@pilot.example", "Demo Supervisor", Role.SUPERVISOR),
        ("agent1@pilot.example", "Demo Agent 01", Role.AGENT),
        ("agent2@pilot.example", "Demo Agent 02", Role.AGENT),
        ("client@pilot.example", "Demo Client Viewer", Role.CLIENT_VIEWER),
    ]
    users: list[User] = []
    for email, display_name, role in user_specs:
        user = db.scalar(select(User).where(User.tenant_id == tenant.id, User.email == email))
        if user is None:
            user = User(tenant_id=tenant.id, email=email, display_name=display_name, password_hash=hash_password(settings.seed_admin_password), role=role)
            db.add(user)
            db.flush()
        users.append(user)

    campaign = db.scalar(select(Campaign).where(Campaign.tenant_id == tenant.id, Campaign.name == "HarperValleyBank Evidence Demo"))
    if campaign is None:
        campaign = Campaign(tenant_id=tenant.id, name="HarperValleyBank Evidence Demo", direction="blended")
        db.add(campaign)
        db.flush()
    queue = db.scalar(select(WorkQueue).where(WorkQueue.tenant_id == tenant.id, WorkQueue.name == "Evidence Demo Queue"))
    if queue is None:
        queue = WorkQueue(tenant_id=tenant.id, campaign_id=campaign.id, name="Evidence Demo Queue", channels=["voice", "web_chat"])
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

    voice_config = db.scalar(select(ChannelConfig).where(ChannelConfig.tenant_id == tenant.id, ChannelConfig.channel == Channel.VOICE))
    if voice_config is None:
        voice_config = ChannelConfig(tenant_id=tenant.id, channel=Channel.VOICE)
        db.add(voice_config)
    voice_config.enabled = True
    voice_config.settings = {
        "provider": "groq_external" if tenant.ai_mode == "external" else "deterministic_local",
        "queue_id": queue.id,
        "sip_extension": "1001",
    }

    if db.scalar(select(ClientAccessGrant.id).where(ClientAccessGrant.user_id == users[4].id, ClientAccessGrant.campaign_id == campaign.id)) is None:
        db.add(ClientAccessGrant(tenant_id=tenant.id, user_id=users[4].id, campaign_id=campaign.id))

    if db.scalar(select(Script.id).where(Script.tenant_id == tenant.id, Script.campaign_id == campaign.id, Script.active.is_(True))) is None:
        db.add(Script(tenant_id=tenant.id, campaign_id=campaign.id, name="Corpus-derived banking call flow", version=1, language="en", content="Derived from the published HarperValleyBank dialog patterns: greet and identify the bank, understand the caller's task, ask only for task-relevant details, answer from the supplied task metadata, offer further help, and close professionally.", required_steps=["Professional greeting", "Understand the caller task", "Provide the source-backed answer", "Offer further help", "Close professionally"]))
    if db.scalar(select(KnowledgeArticle.id).where(KnowledgeArticle.tenant_id == tenant.id, KnowledgeArticle.title == "HarperValleyBank evidence boundary")) is None:
        db.add(KnowledgeArticle(tenant_id=tenant.id, campaign_id=campaign.id, title="HarperValleyBank evidence boundary", language="en", content="Published human-recorded simulated banking calls under CC BY 4.0. These are research-corpus interactions, not production customer calls.", tags=["provenance", "harpervalley", "evidence"]))

    qa_form = db.scalar(select(QAForm).where(QAForm.tenant_id == tenant.id, QAForm.campaign_id == campaign.id, QAForm.name == "Corpus-derived Banking QA", QAForm.version == 1))
    if qa_form is None:
        qa_form = QAForm(tenant_id=tenant.id, campaign_id=campaign.id, name="Corpus-derived Banking QA", version=1)
        db.add(qa_form)
        db.flush()
    if db.scalar(select(QAQuestion.id).where(QAQuestion.form_id == qa_form.id)) is None:
        for position, (label, weight, fatal) in enumerate([
            ("Professional greeting and identification", 20, False),
            ("Understood the caller's stated task", 20, False),
            ("Provided an answer supported by task metadata", 30, True),
            ("Offered further help", 15, False),
            ("Closed the call professionally", 15, False),
        ], start=1):
            db.add(QAQuestion(form_id=qa_form.id, position=position, label=label, guidance=label, weight=weight, fatal=fatal))
    db.commit()
