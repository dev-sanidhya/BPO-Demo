# Verification Record

This file records what was exercised against the current source tree. A source claim is not a verification result.

## Baseline - 2026-08-09

- Python syntax: all 12 pre-existing Python files parsed successfully.
- Docker configuration: `docker compose config --quiet` passed with supplied audit environment values.
- Images: Asterisk, realtime-assist, QA scoring, agent UI, and Metabase provisioner built successfully.
- Containers: Postgres, Asterisk, realtime-assist, QA scoring, and agent UI booted together.
- Browser: agent UI loaded; extension `1001` registered; realtime-assist WebSocket connected; no page console warning/error was observed.
- Telephony: self-contained ARI test originated; two expected Local-channel legs entered Stasis, created Snoop/External Media bridges, and were persisted as ended calls.
- AI: captured chunks reached the configured Groq transcription endpoint, which correctly returned HTTP 401 for the deliberately invalid audit key. A successful external AI run was therefore **not** independently verified in this baseline.
- Data: the QA worker created visible flagged failure records for calls with no successful transcript.
- Worktree: no source changes were introduced by the baseline runtime audit.

## Baseline Defects Promoted to Product Requirements

- Realtime prompts are broadcast to all clients; the current browser client does not implement the filtering claimed in the server comment.
- SIP credentials are accepted through URL parameters.
- Audio is mixed with `spy=both`, so agent/customer attribution is not reliable.
- There is no complete recording archive or synchronized playback.
- The agent page is a test harness, not an operational desktop.
- Metabase is a separate product surface and not a unified client portal.
- The current mandatory Groq path violates strict-local privacy.
- The self-test doubles Local-channel rows.
- Asterisk emits CDR CSV write errors because its target directory is absent.

New implementation layers must add their commands, fixtures, results, and remaining limitations below this baseline.

## Unified API Foundation - 2026-08-09

- Built `services/platform-api` from a clean Python 3.12 image using the pinned dependency set.
- Ran five isolated API tests: authentication/current user, role denial, tenant-scoped assignment and agent work visibility, agent presence, and client-viewer denial. Result: **5 passed**.
- Booted the API against the repository's PostgreSQL 16 service, passed `/health`, authenticated the seeded admin, and confirmed five users plus the login audit event in Postgres.
- Confirmed non-development configuration fails fast when JWT or seed credentials retain development defaults.

The foundation currently owns tenants, users/roles, campaigns, queues/membership, contacts, conversations, messages, agent presence, and audit events. QA, scripts/knowledge, recordings, durable jobs, cost events, survey responses, and channel-specific data remain in subsequent implementation layers.

## Compliance Data Foundation - 2026-08-09

- Expanded the API schema with versioned scripts, knowledge articles, QA forms/questions, automatic evaluations, evidence spans, immutable review history, recordings, actual/predicted satisfaction separation, cost events, and durable jobs.
- Added API acceptance coverage requiring every QA form question to have exactly one answer and every answer to carry timestamped evidence.
- Verified that a supervisor review changes the reviewed score while preserving the original automatic score. Result: **6 API tests passed**.
