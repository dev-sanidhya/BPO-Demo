# BPO AI Platform — Pilot

A self-hosted, all-in-one platform combining an omni-channel dialer, AI-based
call QA/compliance monitoring, real-time in-call agent-assist prompting, and
an analytics dashboard — built for a 2-3 seat pilot before a wider rollout.

Everything runs on your own infrastructure via Docker Compose. The only
external dependency is the Groq API (transcription + LLM scoring/prompting).

**Live-verified end to end** (2026-08-06): a full `docker compose up`, a
no-trunk test call, real Groq transcription of live-tapped audio, real LLM
QA scoring with correct reasoning, and a Metabase dashboard rendering that
data — see "What's been verified" below for the actual run.

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
                     (transcripts table)
                          │
                    qa-scoring service
              (reads transcript chunks already written above →
               Groq Llama rubric score → qa_scores table)
                          │
                       Metabase  (auto-provisioned dashboard)
```

- **Telephony core**: Asterisk 20 on the `andrius/asterisk` image, not
  Vicidial, and not compiled from source. Vicidial is a legacy Perl/PHP/
  MySQL monolith built for a CentOS ISO install — it fights Docker. Building
  Asterisk + PJSIP from source turned out to be its own multi-day rabbit
  hole (Debian bookworm ships no `asterisk` apt package at all, and
  `chan_pjsip` needs PJSIP compiled with specific SRTP/WebRTC flags most
  teams don't hand-roll). `andrius/asterisk` is a well-maintained community
  image with Asterisk 20 + PJSIP + ARI + WebRTC already built correctly, at
  the standard `/etc/asterisk` config path — confirmed live with
  `pjsip show endpoints`, `pjsip show transports`, and `http show status`
  all matching the intended config exactly.
- **One transcript pipeline, not two**: originally this also ran
  `MixMonitor` for a separate full-call recording. Confirmed live that
  `MixMonitor` produced empty (0-frame) `.wav` files when run alongside the
  Snoop-based real-time tap on the same channel — rather than debug that
  conflict, the design now unifies on the Snoop/External Media pipeline
  (already proven to capture real audio correctly): `qa-scoring` scores the
  transcript chunks `realtime-assist` already wrote during the call instead
  of re-transcribing a separate recording. Fewer moving parts, one fewer
  Groq API call per finished call, and no broken component left in place.
- **AI provider**: [Groq](https://console.groq.com) — `whisper-large-v3-turbo`
  for transcription, `llama-3.1-8b-instant` for real-time nudges (speed
  matters most), `llama-3.3-70b-versatile` for post-call QA scoring (quality
  matters most, runs async).
- **Real-time target**: near-real-time, ~12 second chunks — not true
  sub-second streaming. Confirmed live: first chunk fires ~12s into a call,
  not at teardown. Prioritizes a reliable demo over a fragile low-latency
  pipeline.

## Setup

1. `cp .env.example .env` and fill in `GROQ_API_KEY` (get one at
   [console.groq.com](https://console.groq.com/keys)). Change every
   `changeme*` password while you're in there.
2. `docker compose up --build`
3. Wait for all services to report healthy (`docker compose ps`) — Metabase
   in particular takes 60-90s on first boot to run its own internal
   migrations, then:
   - Agent console: http://localhost:8080
   - Metabase dashboard: http://localhost:3000 (login:
     `METABASE_ADMIN_EMAIL` / `METABASE_ADMIN_PASSWORD` from `.env`)

## Testing without a SIP trunk

No carrier, no SIP trunk, and no softphone are required to prove the whole
pipeline end-to-end:

```bash
bash scripts/setup_extensions.sh     # waits for Asterisk, prints connection info
python scripts/make_test_call.py     # places a fully self-contained test call
```

`make_test_call.py` originates a call into Asterisk's `autotest` extension,
which Asterisk answers itself and plays bundled demo audio into (standing in
for "customer speech") — no second party needed. This exercises the full
chain: audio tap → real-time transcription → QA scoring → dashboard, exactly
as a real call would (confirmed live — see below).

Note: originating into a `Local/...@internal` endpoint creates two channel
legs, and both independently run the `autotest` extension's dialplan — so
one `make_test_call.py` run produces two `calls` rows / two sets of
transcripts and scores, not one. Harmless for proving the pipeline works,
but worth knowing before reading dashboard numbers literally. A *real*
two-party call (1001 dialing 1002 via PJSIP) does not have this quirk —
only the caller's channel enters Stasis.

For a real two-party call, register a softphone (Zoiper, Linphone,
MicroSIP) as extension `1002` (see `scripts/setup_extensions.sh` output for
credentials) and dial `1001` from the agent console at
http://localhost:8080, or vice versa.

## What each piece does

| Component | Role |
|---|---|
| `asterisk/` | Telephony core: PJSIP extensions, ARI, dialplan (on `andrius/asterisk:20`, with core sound files added for `Playback()`) |
| `services/qa-scoring/` | Post-call worker: reads the transcript chunks already captured for a finished call and scores them against the rubric in `rubric.py` |
| `services/realtime-assist/` | Taps every live call's audio via ARI Snoop + External Media, chunks it (~12s), transcribes + nudges via Groq, pushes nudges over a websocket, and is the single source of transcript data |
| `services/agent-ui/` | Browser-based WebRTC softphone (open with `?ext=1001` or `?ext=1003`) + live assist panel |
| `dashboard/metabase_provision/` | Auto-creates the Postgres connection, four starter questions, and a dashboard in Metabase on first boot |
| `db/init.sql` | Schema: `calls`, `transcripts`, `qa_scores`, `realtime_prompts` |

## Testing a real two-party browser call

Extensions `1001` and `1003` are both WebRTC-capable specifically so a real
two-party call can be tested entirely in the browser, with two actual
people talking — no desktop softphone needed:

1. Open **http://localhost:8080/?ext=1001&pass=changeme1001** in one tab
   (or device).
2. Open **http://localhost:8080/?ext=1003&pass=changeme1003** in another
   tab (or device, if using a TLS proxy — see tradeoffs below).
3. Wait for both to show "SIP: registered as ...".
4. In the 1001 tab, type `1003` in the dial box and click Call. Accept the
   microphone permission prompt in both tabs.
5. Talk. Both sides should hear each other, and the call is being tapped
   in real time by `realtime-assist` and QA-scored after hangup, same as
   any other call — check the Metabase dashboard afterward.

(`1002` stays plain-UDP for desktop softphone testing per the section
above — it won't work with agent-ui.)

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
  live-assist side of the platform still works regardless (confirmed live
  in-browser: SIP panel shows a clear error, live-assist panel keeps
  reconnecting independently). Vendor a webpack-bundled JsSIP build if full
  offline browser operation is required.
- **WebRTC over plain WS, not WSS-with-real-TLS** by default — browsers
  require HTTPS/secure-context for `getUserMedia` outside `localhost`. Put
  a TLS-terminating reverse proxy (nginx/Caddy) in front for anything
  beyond local testing (a second physical device on the LAN, for example).
  Confirmed live: the actual SIP WebSocket upgrade is served on port 8088
  (Asterisk's shared HTTP/ARI server, `/ws` path) — a raw handshake
  against port 8089 (where `pjsip.conf`'s `transport-ws` section binds)
  gets no response at all. `pjsip.conf` still needs that transport section
  to make `chan_pjsip` accept WebSocket registrations at all; clients just
  connect via 8088 to reach it. `services/agent-ui/app.js` is wired to
  8088 accordingly.
- **Docker anonymous volumes silently shadow config rebuilds** — the
  `andrius/asterisk` base image declares `VOLUME`s including
  `/etc/asterisk`. Confirmed live: after the first `docker compose up`,
  subsequent `docker compose build` + `up` cycles kept serving the
  *original* config from that anonymous volume even though the image
  itself had the new files — normal `--force-recreate` doesn't reseed
  anonymous volumes from a rebuilt image. Any time you edit files under
  `asterisk/conf/` after the first boot, redeploy with
  `docker compose up -d --force-recreate --renew-anon-volumes asterisk`,
  not a plain rebuild+restart, or the change silently won't take effect.
- **No full-call audio archive** — since `MixMonitor` was removed (see
  Architecture above), there's no standalone recording file for a human to
  listen back to. QA scoring works from text transcripts only. If the
  client wants audio playback for a flagged call (common compliance ask),
  that needs its own build: e.g. write the raw audio `realtime-assist`
  already captures per chunk to disk instead of discarding it after
  transcription.
- **Realtime-assist event handling is single-threaded/sequential** — one
  call's Stasis setup (snoop + external media + bridge) is fully handled
  before the next event is processed. Fine at 2-3 seat pilot volume; would
  need reworking (concurrent task dispatch) before scaling toward hundreds
  of seats.
- **DB writes open a short-lived connection per call** rather than sharing
  a pool — simplest safe option at pilot volume, wasteful at real scale.
- **Local-channel test calls double-count** — see "Testing without a SIP
  trunk" above. Real PJSIP-to-PJSIP calls don't have this issue.

## What's been verified

Live-verified end to end against a running Docker Desktop instance
(2026-08-06), via `scripts/make_test_call.py`:

- Asterisk boots clean on `andrius/asterisk:20`; `pjsip show endpoints`,
  `pjsip show transports`, `http show status`, and `dialplan show internal`
  all match the intended config exactly.
- A no-trunk test call flows through Stasis → Snoop + External Media →
  `realtime-assist`'s per-call UDP audio tap.
- Real Groq Whisper transcription of that live-tapped audio produced
  correct text (verified against the actual bundled demo-audio content).
- Real Groq Llama QA scoring ran against those transcripts and produced
  sensible, content-aware output (correctly flagged a call as "not a real
  customer interaction" rather than hallucinating a plausible-looking
  score).
- The Metabase dashboard, logged into directly, rendered that real data:
  call volume chart, QA score chart, and the flagged-calls table showing
  the actual two test-call rows with their real LLM-generated notes.

Bugs found and fixed during this pass (all confirmed live, not
theoretical):

1. Debian bookworm ships no `asterisk` apt package — switched to the
   `andrius/asterisk:20` base image.
2. The base image's `/var/lib/asterisk/sounds` was empty — added the
   official `asterisk-core-sounds-en-wav` package so `Playback()` works.
3. ARI's `POST /channels` origination returned 400 when given only an
   `endpoint=Local/...` param — needs explicit `extension`+`context` too.
   Fixed in `make_test_call.py`.
4. **`StasisEnd` fires the instant a channel's `continue()` is called (i.e.
   milliseconds into the call), not at actual hangup.** The original code
   used it to trigger cleanup, which tore down the audio tap and marked the
   call "ended" before any real audio had been captured. Fixed by switching
   cleanup to the `ChannelDestroyed` event (the real hangup signal).
5. `realtime-assist`'s ARI websocket had no reconnect logic — a dropped
   connection (confirmed by recreating the Asterisk container) left the
   process running but silently deaf to all calls, with no crash and no
   error logged. Fixed with a reconnecting loop with backoff.
6. `qa-scoring` retried permanently-broken recordings forever, hammering
   the Groq API with the same failing request every 5s. Fixed by writing a
   flagged placeholder score on failure so it's surfaced once, not retried
   indefinitely.
7. `MixMonitor` produced empty recordings when run alongside the Snoop tap
   — removed it and unified QA scoring on the already-working real-time
   transcript pipeline (see Architecture above).
8. Extension `1002` (originally the only "customer" endpoint) was plain-UDP
   only, making browser-to-browser testing impossible — added WebRTC
   extension `1003` so a real two-party call can be tested entirely in two
   browser tabs. See "Testing a real two-party browser call" above.
9. agent-ui's SIP WebSocket URL pointed at port 8089 — confirmed live (raw
   WebSocket handshake via `curl` and via browser `WebSocket()`) that 8089
   accepts no HTTP upgrade at all, while port 8088 completes the SIP
   WebSocket handshake correctly. Fixed in `app.js`. See the "WebRTC over
   plain WS" tradeoff above for why 8089 exists at all.
10. Rebuilding the Asterisk image after the first `docker compose up`
    silently had no effect — root-caused to the anonymous-volume issue
    documented above. Any config change after first boot needs
    `--renew-anon-volumes` to actually take effect; this cost significant
    debugging time before being caught via a deliberate marker-string test.

**Measured latency** (from the verified run above, Groq's US infrastructure,
tested from this environment):
- Chunk flush → transcription complete: **~1.4-1.5s** (audio upload +
  `whisper-large-v3-turbo`).
- Transcription → nudge decision complete: **~270-430ms**
  (`llama-3.1-8b-instant`).
- So an agent sees a nudge roughly **~1.7-2s after each 12s chunk closes** —
  well inside the near-real-time target agreed for this build. Also tested
  the nudge path directly with realistic complaint content ("on hold an
  hour, want a manager") rather than the benign demo audio: produced a
  correct, actionable suggestion ("Apologize for the wait and offer to
  escalate the issue immediately") in **315ms**, confirming the nudge logic
  fires correctly when content actually warrants it — the demo audio's
  silence on `realtime_prompts` was the LLM correctly deciding "no nudge
  needed" for a generic message, not a broken path.

**Real two-party browser call — partially verified.** The SIP transport
itself is confirmed live and correct: both `1001` and `1003` register as
`ws` endpoints (`pjsip show endpoints`), and a raw `WebSocket()` connection
from inside a real browser tab to `ws://localhost:8088/ws` completes the
SIP-protocol handshake successfully. What's *not* verified is a full call
with actual two-way audio — the sandboxed browser tool used for this
session blocks the CDN fetch agent-ui needs to load the JsSIP library
(`https://cdn.jsdelivr.net/...`) even though the same URL is reachable via
plain `curl` — that's a restriction specific to this tool's browser
automation, not a bug in the app. **This needs to be tested in a real
browser** (open the two URLs in the "Testing a real two-party browser
call" section above in actual Chrome/Edge/Firefox tabs) before the client
demo — the transport is proven, but the full JsSIP-mediated call/audio
path is not.

## Editing the QA rubric

Edit `services/qa-scoring/rubric.py` — `RUBRIC_PROMPT` is the single place
that defines what "good" looks like for a call (compliance steps, script
adherence, tone). Replace it with the client's actual compliance script and
tone guidelines once they hand those over.
