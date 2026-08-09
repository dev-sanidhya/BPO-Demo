import time

from .database import Base, SessionLocal, engine
from .jobs import claim_recoverable_job, complete_job, record_failure


def run() -> None:
    Base.metadata.create_all(bind=engine)
    while True:
        with SessionLocal() as db:
            job = claim_recoverable_job(db)
            job_id = job.id if job else None
        if job_id is None:
            time.sleep(2)
            continue
        with SessionLocal() as db:
            try:
                complete_job(db, job_id)
            except Exception as error:
                record_failure(db, job_id, error)


if __name__ == "__main__":
    run()
