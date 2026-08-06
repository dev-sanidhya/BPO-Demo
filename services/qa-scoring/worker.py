"""Post-call QA worker: polls Postgres for finished calls with no score yet,
scores them against the rubric, and writes the result back. Runs as a simple
polling loop rather than a message queue — call volume in a 2-3 seat pilot
doesn't need more than that; revisit with a real queue (the Agency repo
already uses Redis + Dramatiq) if this scales past the pilot.

Sources its transcript from the `transcripts` table that realtime-assist
already writes progressively during the call (via its Snoop + External
Media audio tap), rather than doing a second, separate transcription of a
full-call MixMonitor recording. Confirmed live that MixMonitor produced
empty (0-frame) recordings when run alongside the Snoop tap on the same
channel — rather than debug that conflict, this unifies on the transcript
pipeline already proven to work, and avoids a redundant Whisper call per
finished call."""
import logging
import os
import time

import db
import groq_client
from rubric import RUBRIC_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s qa-scoring %(message)s")
log = logging.getLogger("qa-scoring")

POLL_SECONDS = float(os.environ.get("QA_POLL_SECONDS", "5"))


def process_call(conn, call_id: str) -> None:
    chunks = db.fetch_transcript_chunks(conn, call_id)
    if not chunks:
        log.info("call %s has no captured transcript chunks, flagging for review", call_id)
        db.insert_qa_score(conn, call_id, {
            "overall_score": None,
            "flagged": True,
            "notes": "No audio was captured for this call (too short, or the "
                     "realtime-assist tap never attached) — needs manual review.",
        })
        return

    full_transcript = " ".join(chunk["text"] for chunk in chunks)
    log.info("scoring call %s (%d transcript chunks)", call_id, len(chunks))
    scores = groq_client.score_transcript(full_transcript, RUBRIC_PROMPT)
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
                    process_call(conn, row["call_id"])
                except Exception as exc:
                    # Confirmed live: without writing a placeholder score, a
                    # permanently-broken call gets retried every poll cycle
                    # forever, hammering the Groq API with the same failing
                    # request indefinitely. Flag it instead so a human sees
                    # it once in the dashboard and it stops being retried.
                    log.exception("failed to process call %s, marking as flagged", row["call_id"])
                    conn.rollback()
                    try:
                        db.insert_qa_score(conn, row["call_id"], {
                            "overall_score": None,
                            "flagged": True,
                            "notes": f"QA scoring failed: {exc}",
                        })
                    except Exception:
                        log.exception("also failed to write failure placeholder for %s", row["call_id"])
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
