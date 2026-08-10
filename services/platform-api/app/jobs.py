from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .local_voice import finalize_local_voice
from .external_voice import finalize_external_voice
from .models import Conversation, DurableJob, JobStatus, Tenant


VOICE_FINALIZE = "voice.finalize"


def start_voice_finalization(db: Session, conversation: Conversation) -> DurableJob:
    tenant = db.get(Tenant, conversation.tenant_id)
    job = DurableJob(
        tenant_id=conversation.tenant_id,
        job_type=VOICE_FINALIZE,
        payload={"conversation_id": conversation.id, "ai_mode": tenant.ai_mode if tenant else "local"},
        status=JobStatus.PENDING,
        attempts=0,
        available_at=datetime.now(timezone.utc),
        locked_at=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def complete_job(db: Session, job_id: str) -> None:
    job = db.get(DurableJob, job_id)
    if job is None or job.status == JobStatus.SUCCEEDED:
        return
    conversation = db.get(Conversation, job.payload["conversation_id"])
    if conversation is None:
        raise ValueError("Conversation for durable job no longer exists")
    if job.payload.get("ai_mode") == "external":
        finalize_external_voice(db, conversation)
    else:
        finalize_local_voice(db, conversation)
    job.status = JobStatus.SUCCEEDED
    job.locked_at = None
    job.last_error = None
    db.commit()


def record_failure(db: Session, job_id: str, error: Exception) -> None:
    db.rollback()
    job = db.get(DurableJob, job_id)
    if job is None:
        return
    job.last_error = str(error)[:2000]
    job.locked_at = None
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.FAILED
    else:
        job.status = JobStatus.PENDING
        job.available_at = datetime.now(timezone.utc) + timedelta(seconds=min(5 * job.attempts, 60))
    db.commit()


def claim_recoverable_job(db: Session) -> DurableJob | None:
    now = datetime.now(timezone.utc)
    # Provider-backed transcription and rubric evaluation can legitimately take
    # several minutes under rate limiting. Do not let another worker reclaim a
    # healthy in-flight job and create duplicate QA evidence.
    stale = now - timedelta(minutes=15)
    job = db.scalar(
        select(DurableJob)
        .where(
            DurableJob.job_type == VOICE_FINALIZE,
            DurableJob.attempts < DurableJob.max_attempts,
            or_(
                (DurableJob.status == JobStatus.PENDING) & (DurableJob.available_at <= now),
                (DurableJob.status == JobStatus.RUNNING) & (DurableJob.locked_at < stale),
            ),
        )
        .order_by(DurableJob.available_at)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.locked_at = now
    db.commit()
    db.refresh(job)
    return job
