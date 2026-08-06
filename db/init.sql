-- Core schema for the BPO AI platform pilot.
-- Applied automatically on first Postgres boot via docker-entrypoint-initdb.d.

CREATE TABLE IF NOT EXISTS calls (
    call_id         TEXT PRIMARY KEY,           -- Asterisk UNIQUEID
    agent_ext       TEXT,
    call_type       TEXT,                       -- 'agent' | 'customer' | 'autotest'
    direction       TEXT DEFAULT 'internal',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    recording_path  TEXT
);

CREATE TABLE IF NOT EXISTS transcripts (
    id              BIGSERIAL PRIMARY KEY,
    call_id         TEXT NOT NULL REFERENCES calls(call_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_transcripts_call_id ON transcripts(call_id);

CREATE TABLE IF NOT EXISTS qa_scores (
    call_id                  TEXT PRIMARY KEY REFERENCES calls(call_id) ON DELETE CASCADE,
    compliance_score         NUMERIC(5,2),
    script_adherence_score   NUMERIC(5,2),
    tone_score                NUMERIC(5,2),
    overall_score             NUMERIC(5,2),
    notes                     TEXT,
    flagged                   BOOLEAN NOT NULL DEFAULT false,
    scored_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS realtime_prompts (
    id              BIGSERIAL PRIMARY KEY,
    call_id         TEXT NOT NULL REFERENCES calls(call_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    prompt_text     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_realtime_prompts_call_id ON realtime_prompts(call_id);
