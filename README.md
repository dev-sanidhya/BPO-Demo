# Aperture CX

A pilot-ready, self-hosted BPO operations platform that combines four workflows in one product:

1. Inbound/outbound voice and digital conversation handling.
2. Evidence-linked AI QA, compliance, script, and tone monitoring.
3. Contextual live agent assistance and campaign knowledge.
4. Supervisor/client reporting with actual CSAT, predicted risk, exports, and unit economics.

The recommended product shape is implemented: agents use an installable Electron desktop, while supervisors, QA reviewers, administrators, and restricted client viewers use the same branded web console. Both surfaces share one API, identity model, authorization boundary, conversation history, QA evidence, configuration, and reporting layer.

## What works now

- Roles: admin, supervisor, QA reviewer, agent, and campaign-scoped client viewer.
- Unified voice and web-chat queue, assignment, agent states, messages, wrap-up, summary, and disposition.
- Voice accept/reject, outbound dial, mute, hold, resume, transfer, hang-up, recording, speaker-attributed transcript, synchronized playback, assist, QA, predicted risk, and cost events.
- Web-chat customer widget with English, Hindi, Marathi, and Hinglish selection, agent replies, resolution, and actual 1-5 CSAT collection.
- Configurable campaign, queue, script, knowledge article, QA form, privacy mode, and role-based user provisioning.
- Automatic QA with timestamped evidence, immutable original score, and reasoned human override.
- Reports filtered by campaign, queue, channel, and agent, with campaign-scoped client access and matching CSV/PDF exports.
- Groq-backed AI is the default processing route for real transcription, guidance, retrieval, summaries, evidence-linked QA, risk prediction, and measured per-call AI cost. Missing credentials fail startup visibly; strict-local deterministic processing remains an explicit admin-selected fallback/test mode.
- Carrier-free two-party WebRTC in both directions: the Electron agent registers as SIP 1001, a browser customer as 1003, and Asterisk routes outbound extension 2003 and inbound extension 2101 through the same recording/AI/QA pipeline.
- Health, privacy/provider status, queue lag, recording storage, realtime event isolation, and audit events.

The default visible dataset contains four CC-BY-4.0 human-performed simulated banking calls from HarperValleyBank plus one explicitly labelled transcript-channel replay. Each record carries source, license, hashes, transformation history, and an honest production-data boundary in the UI. The current licensed call set is English. Hindi, Marathi, and Hinglish processing paths remain available, but Marathi is visibly review-required based on the existing small benchmark. A production carrier trunk, 700-seat capacity/HA certification, predictive dialing, workforce management, native WhatsApp onboarding, and screen recording are post-pilot work, not current claims.

## Architecture

```text
Electron agent desktop --+
Web operations portal ----+-- FastAPI platform API -- PostgreSQL
Customer web chat --------+             |
                                        +-- recording/transcript/QA evidence
                                        +-- realtime authorized events
                                        +-- Groq AI / Asterisk WebRTC
```

The default Compose stack is AI-first: `postgres`, `platform-api`, durable `platform-worker`, `console`, and `asterisk`. Voice evidence is recorded as a durable job before processing; a worker retries abandoned or transiently failed jobs. Groq is the default provider inside that pipeline. The lightweight browser SIP endpoint and Metabase remain optional profiles.

## Quick start

Prerequisites: Docker Desktop and the packaged desktop build. Node.js 22+ is needed only when rebuilding.

```powershell
# The launcher safely reads GROQ_API_KEY from the Windows User environment.
powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
```

Open:

- Operations portal: http://localhost:18081
- API health: http://localhost:18080/health
- Customer widget: http://localhost:18081/?widget=1
- Talkable browser customer endpoint: http://localhost:18082/?ext=1003&pass=changeme1003&assist=0&target=2101

See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for the exact outbound, inbound, supervisor, QA, reports, and client-viewer walkthrough.

Seeded local-pilot identities all use `PLATFORM_SEED_ADMIN_PASSWORD`:

| Role | Email |
|---|---|
| Admin | `admin@pilot.example` |
| Supervisor | `supervisor@pilot.example` |
| QA reviewer | `qa@pilot.example` if provisioned by the admin; otherwise create one in Settings |
| Agent 1 | `agent1@pilot.example` |
| Agent 2 | `agent2@pilot.example` |
| Client viewer | `client@pilot.example` |

The seed is for a local demonstration. Use production secrets, TLS, backups, retention policy, and identity integration before a real deployment.

## Windows agent desktop

```powershell
Set-Location apps\console
npm ci
npm run electron:dev
npm run electron:dist:win
```

The installer is written to `apps/console/release/Aperture CX Agent Setup 0.1.0.exe`. The desktop expects the API at `http://localhost:18080` by default; set `PLATFORM_API_URL` before launch when the on-prem server uses another address.

### Default Groq AI mode

Set `GROQ_API_KEY` in the local untracked `.env` or the current process environment before starting Compose. `scripts\start_demo.ps1` safely inherits it from the Windows User environment. New deployments start in `external` mode and refuse to report ready when that credential is missing. The selected defaults are `whisper-large-v3` for realtime/final ASR and `openai/gpt-oss-20b` for guidance and QA. This sends call audio/transcript context to Groq; the UI and diagnostics say so explicitly. An admin can deliberately select strict-local deterministic mode for privacy-constrained testing, but that mode is not generative AI.

### Carrier-free live calls

```powershell
$env:AGENT_UI_PORT='18082'
docker compose --profile legacy-ui up -d --build agent-ui

Set-Location apps\console
$env:PLATFORM_SIP_ENABLED='true'
npm run electron:dev
```

Open `http://localhost:18082/?ext=1003&pass=changeme1003&assist=0&target=2101`, allow microphone access, then dial `2003` from Electron for outbound. Click **Call** in the browser for inbound through Asterisk route `2101 -> 1001`. These are real same-machine WebRTC/SIP media paths, not PSTN. Replace the demo SIP passwords before any shared network use. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for carrier onboarding.

## Reproducible verification

```powershell
python scripts\verify_voice_fixture.py
docker compose config --quiet
docker compose build platform-api platform-worker console
docker run --rm -v "${PWD}\services\platform-api\tests:/app/tests:ro" bpo-demo-platform-api pytest -q

Set-Location apps\console
npm run build
npm run test:e2e:web
npm run test:e2e:electron
npm run test:e2e:sip
npm run electron:dist:win
npm run test:e2e:packaged
```

The browser checks use installed Chrome and exercise desktop and mobile layouts, interactions, downloads, CSAT, client restrictions, console output, failed network requests, and overflow. The Electron checks exercise the complete agent workflow and the packaged Windows executable. Current results and evidence paths are in [docs/VERIFICATION.md](docs/VERIFICATION.md).

For the same checks as one command, run `powershell -ExecutionPolicy Bypass -File scripts\verify_all.ps1`; add `-IncludePackage` to rebuild and smoke-test the Windows installer.

## Market position

Genesys, NICE, Five9, Observe.AI, Cresta, Ameyo, and Exotel establish the table stakes: operational routing, recording, QA, assist, knowledge, omnichannel context, and reporting. Aperture CX does not claim broader suite parity. Its credible pilot advantages are verifiable local data custody, one integrated 1-3 seat proof, evidence-linked QA, India-language digital workflows, transparent per-interaction economics, deployment ownership, and actual survey values kept distinct from AI predictions. See [docs/COMPETITOR_MATRIX.md](docs/COMPETITOR_MATRIX.md).

## Repository map

- `apps/console/`: React operations portal, customer widget, Electron shell, and UI E2E tests.
- `services/platform-api/`: tenant-aware FastAPI application, durable worker, data model, authorization, local voice evidence, reporting, and API tests.
- `asterisk/`: Asterisk 20 configuration and telephony extension point.
- `asterisk/test-audio/`: licensed real-call provenance plus reproducible synchronized English/Hindi/Marathi/Hinglish fixtures and manifests.
- `docs/PRODUCT_CONTRACT.md`: scope, invariants, deferred work, and acceptance scenario.
- `docs/COMPETITOR_MATRIX.md`: primary-source market comparison and claim boundaries.
- `docs/QA_INVENTORY.md`: baseline audit and reusable defect inventory.
- `docs/VERIFICATION.md`: commands, results, and remaining limits.

## Optional auxiliary profiles

These are retained for reference and are not part of the default verified platform path:

```powershell
docker compose --profile external-ai up -d
docker compose --profile legacy-ui up -d
docker compose --profile legacy-dashboard up -d
```

The primary Groq implementation runs in `platform-api`/`platform-worker`; the older `external-ai` profile is retained only for reference. Any Groq processing sends customer content to a third party and therefore does not satisfy strict-local mode.
