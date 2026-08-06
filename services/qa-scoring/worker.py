"""Post-call QA worker: polls Postgres for finished calls with no score yet,
transcribes the recording, scores it against the rubric, and writes the
result back. Runs as a simple polling loop rather than a message queue —
call volume in a 2-3 seat pilot doesn't need more than that; revisit with a
real queue (the Agency repo already uses Redis + Dramatiq) if this scales
past the pilot."""
import logging
import os
import time

import db
import groq_client
from rubric import RUBRIC_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s qa-scoring %(message)s")
log = logging.getLogger("qa-scoring")

RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "/recordings")
POLL_SECONDS = float(os.environ.get("QA_POLL_SECONDS", "5"))


def process_call(conn, call_id: str, recording_path: str) -> None:
    wav_path = os.path.join(RECORDINGS_DIR, os.path.basename(recording_path))
    if not os.path.exists(wav_path):
        log.warning("recording not found on disk yet, will retry: %s", wav_path)
        return

    log.info("transcribing call %s (%s)", call_id, wav_path)
    transcript = groq_client.transcribe_file(wav_path)
    db.insert_transcript(conn, call_id, chunk_index=0, text=transcript)

    log.info("scoring call %s", call_id)
    scores = groq_client.score_transcript(transcript, RUBRIC_PROMPT)
    db.insert_qa_score(conn, call_id, scores)
    log.info(
        "call %s scored: overall=%s flagged=%s",
        call_id, scores.get("overall_score"), scores.get("flagged"),
    )


def main() -> None:
    log.info("qa-scoring worker starting, polling every %ss", POLL_SECONDS)
    conn = db.connect()
    while True:
        try:
            pending = db.fetch_calls_pending_scoring(conn)
            for row in pending:
                try:
                    process_call(conn, row["call_id"], row["recording_path"])
                except Exception:
                    log.exception("failed to process call %s", row["call_id"])
                    conn.rollback()
        except Exception:
            log.exception("polling loop error, reconnecting")
            try:
                conn.close()
            except Exception:
                pass
            conn = db.connect()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
