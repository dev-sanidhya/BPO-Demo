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

