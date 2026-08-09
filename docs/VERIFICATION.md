# Verification Record

Last verified: 2026-08-09. Results below are from the current source tree and a live Docker Desktop deployment on Windows. They do not imply 700-seat capacity certification.

## Final Acceptance Result

| Layer | Result | Evidence |
|---|---|---|
| Voice fixture | Pass | `python scripts\verify_voice_fixture.py`: 33,152 ms, 6 non-overlapping segments, agent + customer speakers. |
| Frontend build | Pass | TypeScript project build and Vite production bundle; 1,792 modules transformed. |
| API tests | Pass | 15 tests passed. One upstream Starlette `httpx` deprecation warning; no test failures. |
| Compose validation/build | Pass | `docker compose config --quiet` and default-stack image builds passed. |
| Running default stack | Pass | PostgreSQL, API, durable worker, console, and Asterisk running; PostgreSQL/API/Asterisk healthy. API `/health` returned `{"status":"ok"}`. |
| Asterisk extension point | Pass | `pjsip show endpoints` returned configured endpoints 1001, 1002, and 1003. They remain unavailable until clients register, as expected. |
| Web E2E | Pass | Installed Chrome at 1600x900 and mobile 375x812; no overflow, console warnings/errors, or failed requests. |
| Electron source E2E | Pass | Full chat + inbound/outbound voice agent workflow; native 1426x779 viewport; no overflow, console warnings/errors, or failed requests. |
| Windows package | Pass | NSIS installer built successfully and packaged executable passed login/runtime smoke test. |
| Strict-local boundary | Pass | Voice finalization completed while outbound socket connections were forced to fail. Diagnostics reported local rules and `customer_content_egress=false`. |

## API Acceptance Coverage

The isolated API suite verifies:

- Login/current-user identity and role denial.
- Tenant/campaign scoped conversations, queues, configuration, reports, and client access.
- Queue membership, assignment, presence, claim, and wrap-up.
- Server-authorized realtime events with a negative assertion that an unrelated agent receives no assigned event.
- Web-chat session security, ordered two-way messages, status, close, and actual 1-5 CSAT collection.
- Inbound voice reject/accept and outbound voice dial.
- Mute, hold, resume, transfer, hang-up, recording, two-speaker transcript, assist, evidence-linked QA, CSV/PDF exports, and separated cost categories.
- Durable voice-finalization success state, retry metadata, stale-lock recovery, and job counts in diagnostics.
- Immutable automatic QA score plus reviewed score and reason.
- Strict-local voice evidence processing with network connections blocked.
- Admin campaign/queue/script/knowledge/QA configuration and user provisioning.
- Actual survey CSAT kept separate from predicted satisfaction risk.

Command:

```powershell
docker run --rm -v "C:\CS\Agency\BPO-Demo\services\platform-api\tests:/app/tests:ro" bpo-demo-platform-api pytest -q
```

Result: `15 passed, 1 warning in 22.13s`.

## Browser Acceptance Coverage

`npm run test:e2e:web` verified:

- Invalid login feedback and supervisor login.
- Operations overview, conversation explorer, and QA evidence.
- Human QA override to 91 while the original automatic score of 88 remained visible.
- Report filters, CSV download, and valid PDF download.
- Admin operating-model save and new role-user provisioning.
- Client-viewer access without QA override controls.
- Marathi mobile customer chat, agent claim/reply/wrap-up, resolved state, and recorded 5/5 CSAT.
- Desktop and mobile horizontal-fit assertions.
- Zero captured browser console warnings/errors and zero failed requests.

Result:

```json
{"ok":true,"desktopFit":{"width":1600,"scrollWidth":1600},"mobileFit":{"width":375,"scrollWidth":375},"pages":["Aperture CX","Aperture CX"]}
```

Screenshots are written to `artifacts/ui/`, including:

- `web-supervisor-dashboard.png`
- `web-quality-review.png`
- `web-reports-costs.png`
- `web-admin-configuration.png`
- `mobile-customer-widget.png`
- `mobile-customer-survey.png`

## Electron Acceptance Coverage

`npm run test:e2e:electron` creates exact interaction IDs and verifies:

- Agent login and work queue.
- Exact web-chat claim, reply, customer-side visibility, and wrap-up.
- Exact inbound voice rejection and acceptance.
- Mute/unmute, hold/resume, transfer, and hang-up.
- Playable recording, synchronized transcript, agent/customer labels, assist guidance, and required-step completion.
- Outbound deterministic voice interaction and wrap-up.
- Native-window fit plus zero captured console/network failures.

Result:

```json
{"ok":true,"title":"Aperture CX","fit":{"width":1426,"height":779,"scrollWidth":1426,"scrollHeight":779}}
```

Screenshots: `artifacts/ui/electron-agent-workspace.png`, `electron-active-conversation.png`, and `electron-voice-evidence.png`.

The installer command `npm run electron:dist:win` produced:

- `apps/console/release/Aperture CX Agent Setup 0.1.0.exe` (101,681,888 bytes in this run).
- `apps/console/release/win-unpacked/Aperture CX Agent.exe`.

`npm run test:e2e:packaged` then launched that packaged executable, logged in, rendered the agent workspace, and passed the same 1426x779 fit check.

## Privacy and Data Semantics

- The verified default path uses deterministic local rules and local fixture/recording storage; no external AI credential is required.
- External Groq workers are behind the `external-ai` Compose profile and are not part of the strict-local claim.
- Every protected conversation read is tenant scoped. Client viewers are additionally campaign scoped on conversations, QA, reports, queues, and configuration.
- Actual survey CSAT and predicted satisfaction risk are separate fields, counts, labels, and report values.
- Human review does not overwrite the automatic QA result.

## Honest Pilot Boundaries

Verified:

- One unified voice + web-chat pilot workflow for 1-3 seats.
- A deterministic synchronized English voice evidence lane.
- English/Hindi/Marathi/Hinglish digital selection and Marathi/code-switched browser fixtures.
- An installable Windows agent desktop plus web operations/client portal.

Not yet verified or claimed:

- Live PSTN/SIP carrier onboarding and production trunk failover.
- Native WhatsApp/Meta onboarding.
- Real-time ASR/LLM accuracy or latency on the new strict-local path; the synchronized voice lane is deterministic.
- 700 concurrent seats, high availability, disaster recovery, or formal load certification.
- Predictive/progressive dialing, workforce scheduling, screen recording, or automated customer voice agents.
- Code-signed Windows publisher identity or a custom application icon; the current installer uses Electron's default icon.

The Asterisk base image logs non-required module warnings for unused CDR/CEL/OGG modules. The configured PJSIP endpoints and health check still pass; those warnings do not affect the deterministic pilot lane.
