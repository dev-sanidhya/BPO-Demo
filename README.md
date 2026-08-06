# BPO AI Platform — Pilot

A self-hosted, all-in-one platform combining an omni-channel dialer, AI-based
call QA/compliance monitoring, real-time in-call agent-assist prompting, and
an analytics dashboard — built for a 2-3 seat pilot before a wider rollout.

Everything runs on your own infrastructure via Docker Compose. The only
external dependency is the Groq API (transcription + LLM scoring/prompting).

## Architecture

```
                    ┌──────────────────────────────────────────┐
                    │              Asterisk (PJSIP + ARI)        │
  agent-ui  ───WSS──▶  ext 1001 (agent)   ext 1002 (customer)   │
  (browser)          │        \                /                │
                    │      Stasis(assist_app) — every call      │
                    └───────────────┬────────────────────────────┘
                                    │ Snoop + External Media (RTP)
                                    ▼
                        realtime-assist service
              (per-call audio tap → ~12s chunks →
               Groq Whisper → Groq Llama nudge → websocket)
                          │                    │
                     Postgres            agent-ui (live assist panel)
                          ▲
                          │ post-call recording
                    qa-scoring service
              (Groq Whisper transcript → Groq Llama
               rubric score → qa_scores table)
                          │
                       Metabase  (auto-provisioned dashboard)
```

- **Telephony core**: Asterisk (PJSIP + ARI), not Vicidial — Vicidial is a
  legacy CentOS-install monolith that fights Docker. Building directly on
  Asterisk gives full control over the audio pipeline and a clean
  `docker compose up`.
- **AI provider**: [Groq](https://console.groq.com) — `whisper-large-v3-turbo`
  for transcription, `llama-3.1-8b-instant` for real-time nudges (speed
  matters most), `llama-3.3-70b-versatile` for post-call QA scoring (quality
  matters most, runs async).
- **Real-time target**: near-real-time, ~12 second chunks — not true
  sub-second streaming. Prioritizes a reliable demo over a fragile
  low-latency pipeline.

## Setup

1. `cp .env.example .env` and fill in `GROQ_API_KEY` (get one at
   [console.groq.com](https://console.groq.com/keys)). Change every
   `changeme*` password while you're in there.
2. `docker compose up --build`
3. Wait for all services to report healthy (`docker compose ps`), then:
   - Agent console: http://localhost:8080
   - Metabase dashboard: http://localhost:3000 (login:
     `METABASE_ADMIN_EMAIL` / `METABASE_ADMIN_PASSWORD` from `.env`)

## Testing without a SIP trunk

No carrier, no SIP trunk, and no softphone are required to prove the whole
pipeline end-to-end:

```bash
python scripts/setup_extensions.sh   # waits for Asterisk, prints connection info
python scripts/make_test_call.py     # places a fully self-contained test call
```

`make_test_call.py` originates a call into Asterisk's `autotest` extension,
which Asterisk answers itself and plays bundled demo audio into (standing in
for "customer speech") — no second party needed. This exercises the full
chain: recording → QA scoring → real-time assist → dashboard, exactly as a
real call would.

For a real two-party call, register a softphone (Zoiper, Linphone,
MicroSIP) as extension `1002` (see `scripts/setup_extensions.sh` output for
credentials) and dial `1001` from the agent console at
http://localhost:8080, or vice versa.

## What each piece does

| Component | Role |
|---|---|
| `asterisk/` | Telephony core: PJSIP extensions, ARI, call recording, dialplan |
| `services/qa-scoring/` | Post-call worker: transcribes + scores each finished call against the rubric in `rubric.py` |
| `services/realtime-assist/` | Taps every live call's audio via ARI Snoop + External Media, chunks it, and pushes live nudges over a websocket |
| `services/agent-ui/` | Browser-based WebRTC softphone (extension 1001) + live assist panel |
| `dashboard/metabase_provision/` | Auto-creates the Postgres connection, four starter questions, and a dashboard in Metabase on first boot |
| `db/init.sql` | Schema: `calls`, `transcripts`, `qa_scores`, `realtime_prompts` |

## Known tradeoffs (raise these with the client before scaling past the pilot)

- **Audio and transcripts leave the server** to hit the Groq API. If
  "self-hosted" is meant to mean *zero* external calls, this needs a
  self-hosted open-weight LLM/ASR instead — real GPU hardware requirement,
  noticeably weaker scoring quality. Not implemented here; flagged as a
  decision point.
- **agent-ui's SIP library loads from a CDN at runtime** (JsSIP hasn't
  shipped a self-contained browser bundle since ~v3.5 — every recent
  version expects a bundler). If the agent's browser has no internet
  access, the dialer panel will fail to load — but is isolated so the QA/
  live-assist side of the platform still works regardless (see the comment
  in `services/agent-ui/app.js`). Vendor a webpack-bundled JsSIP build if
  full offline browser operation is required.
- **WebRTC over plain WS, not WSS-with-real-TLS** by default — browsers
  require HTTPS/secure-context for `getUserMedia` outside `localhost`. Put
  a TLS-terminating reverse proxy (nginx/Caddy) in front for anything
  beyond local testing.
- **Realtime-assist event handling is single-threaded/sequential** — one
  call's Stasis setup (snoop + external media + bridge) is fully handled
  before the next event is processed. Fine at 2-3 seat pilot volume; would
  need reworking (concurrent task dispatch) before scaling toward hundreds
  of seats.
- **DB writes open a short-lived connection per call** rather than sharing
  a pool — simplest safe option at pilot volume, wasteful at real scale.

## What's been verified vs. what needs a live check

Verified in this environment: `docker-compose.yml` config validity, all
Python services import cleanly against their pinned dependency versions,
shell/JSON syntax, and the agent-ui page (SIP-load failure is isolated from
the live-assist panel, confirmed in-browser).

**Not yet verified live** (this sandbox has the Docker CLI but no running
Docker daemon): the Asterisk PJSIP/ARI/WebRTC config, the ARI Snoop +
External Media audio tap pattern in `ari_listener.py`, and the Metabase
provisioning API calls in `provision.py`. These are written to the
documented, standard patterns for each system, but Asterisk config in
particular is sensitive to exact version behavior — run
`docker compose up`, work through the test-call flow above, and check logs
(`docker compose logs asterisk realtime-assist qa-scoring`) before relying
on this for the actual client demo. Budget time for this pass.

## Editing the QA rubric

Edit `services/qa-scoring/rubric.py` — `RUBRIC_PROMPT` is the single place
that defines what "good" looks like for a call (compliance steps, script
adherence, tone). Replace it with the client's actual compliance script and
tone guidelines once they hand those over.
