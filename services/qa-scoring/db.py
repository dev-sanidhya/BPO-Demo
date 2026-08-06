import os

import psycopg2
import psycopg2.extras


def connect():
    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ.get("POSTGRES_PORT", "5432"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def fetch_calls_pending_scoring(conn, limit: int = 5):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT c.call_id, c.recording_path
            FROM calls c
            LEFT JOIN qa_scores q ON q.call_id = c.call_id
            WHERE c.ended_at IS NOT NULL
              AND c.recording_path IS NOT NULL
              AND q.call_id IS NULL
            ORDER BY c.ended_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def insert_transcript(conn, call_id: str, chunk_index: int, text: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO transcripts (call_id, chunk_index, text)
            VALUES (%s, %s, %s)
            """,
            (call_id, chunk_index, text),
        )
    conn.commit()


def insert_qa_score(conn, call_id: str, scores: dict):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qa_scores
                (call_id, compliance_score, script_adherence_score,
                 tone_score, overall_score, notes, flagged)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (call_id) DO UPDATE SET
                compliance_score = EXCLUDED.compliance_score,
                script_adherence_score = EXCLUDED.script_adherence_score,
                tone_score = EXCLUDED.tone_score,
                overall_score = EXCLUDED.overall_score,
                notes = EXCLUDED.notes,
                flagged = EXCLUDED.flagged,
                scored_at = now()
            """,
            (
                call_id,
                scores.get("compliance_score"),
                scores.get("script_adherence_score"),
                scores.get("tone_score"),
                scores.get("overall_score"),
                scores.get("notes"),
                bool(scores.get("flagged", False)),
            ),
        )
    conn.commit()
