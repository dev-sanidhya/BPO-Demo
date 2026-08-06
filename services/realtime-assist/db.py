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


def upsert_call_started(conn, call_id: str, call_type: str, agent_ext: str | None):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO calls (call_id, agent_ext, call_type, started_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (call_id) DO NOTHING
            """,
            (call_id, agent_ext, call_type),
        )
    conn.commit()


def mark_call_ended(conn, call_id: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE calls
            SET ended_at = now()
            WHERE call_id = %s
            """,
            (call_id,),
        )
    conn.commit()


def insert_transcript_chunk(conn, call_id: str, chunk_index: int, text: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO transcripts (call_id, chunk_index, text)
            VALUES (%s, %s, %s)
            """,
            (call_id, chunk_index, text),
        )
    conn.commit()


def insert_realtime_prompt(conn, call_id: str, chunk_index: int, prompt_text: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO realtime_prompts (call_id, chunk_index, prompt_text)
            VALUES (%s, %s, %s)
            """,
            (call_id, chunk_index, prompt_text),
        )
    conn.commit()
