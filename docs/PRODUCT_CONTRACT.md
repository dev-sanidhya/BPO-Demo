# Unified BPO AI Platform - Product Contract

Last updated: 2026-08-09

## Buyer Contract

The product is a new, independent contact-centre platform. It does not depend on or integrate with the prospect's incumbent dialer. It must be deployable on the BPO's own infrastructure and prove its economics on 1-3 seats before any wider rollout.

The four inseparable product pillars are:

1. Omnichannel contact handling and dialing.
2. AI quality, compliance, script, and tone monitoring.
3. Contextual live agent assistance.
4. Intelligent supervisor and client reporting.

## Recommended Product Shape

- **Agent Desktop:** signed Electron application for voice and digital work, live assistance, scripts, knowledge, and wrap-up.
- **Operations Portal:** branded browser application for supervisors, QA reviewers, administrators, and restricted client viewers.
- **On-Prem Platform:** API, Asterisk, Postgres, recording storage, durable jobs, channel adapters, analytics, and local/external AI providers.

The desktop and portal are two role-specific surfaces of one product, backed by the same identities, permissions, conversation records, configuration, and reporting definitions.

## Pilot Scope

### Required

- Secure login and RBAC for admin, supervisor, QA reviewer, agent, and client viewer.
- Agent availability states and assigned work queues.
- Inbound and outbound voice through a configurable SIP trunk or deterministic local test trunk.
- Call controls: accept/reject, dial, hang up, mute, hold, transfer, and disposition.
- Contacts, campaigns, queues, assignments, scripts, and wrap-up.
- Complete call recording with synchronized transcript playback.
- Speaker-aware transcript with agent and customer attribution.
- Live transcript, smart checklist, compliance reminders, knowledge suggestions, and next-best action.
- Per-agent event isolation; supervisors may observe only within their authorized scope.
- Configurable QA forms, weighted questions, fatal rules, evidence spans, manual review, override, and audit history.
- Real CSAT/DSAT survey values separated from predicted satisfaction risk.
- Unified reporting by client, campaign, queue, channel, team, and agent with CSV/PDF export.
- A real web-chat channel using the same queue, agent, transcript, QA, wrap-up, and reporting model.
- Strict local mode with no customer content leaving the deployment, plus an explicit optional external-AI mode.
- English, Hindi, Marathi, and code-switched sample verification.
- Health, provider, queue-lag, storage, and failure visibility.
- Reproducible Docker deployment and Electron packaging.

### Deferred Until After Pilot Proof

- Predictive/progressive dialer algorithms at production scale.
- Workforce forecasting and scheduling.
- Screen recording.
- Native WhatsApp production onboarding, which requires client-owned Meta credentials and approval.
- Social network adapters.
- Automated customer-facing voice agents.
- 700-seat load certification and high availability.

Deferred items must have explicit extension points, but no placeholder UI may imply that they already work.

## Product Invariants

- `tenant_id` and authorization scope are enforced server-side on every protected record and event.
- No realtime event is broadcast globally without a server-authorized audience.
- Voice and digital interactions use one `conversation` model.
- Every automatic QA answer stores its rule version, model/provider, confidence, and evidence.
- A supervisor override never destroys the original automatic result.
- Predictions are labelled as predictions and never shown as collected survey responses.
- Strict-local mode has an automated egress verification check.
- Provider failure cannot silently produce a successful score.
- Credentials never travel in URL query parameters.
- A product capability is reported as working only after its acceptance scenario passes.

## Pilot Acceptance Scenario

1. An administrator configures a client, campaign, queue, users, script, knowledge base, QA form, and AI privacy mode.
2. Two agents sign into packaged desktop applications and enter available state.
3. One agent handles a real or deterministic SIP voice interaction while the other remains isolated.
4. Only the assigned agent sees the transcript and guidance. An authorized supervisor sees the live interaction.
5. The call produces a playable recording, speaker-attributed transcript, wrap-up, summary, disposition, evidence-linked QA result, and analytics events.
6. A QA reviewer changes one result with a reason; both automatic and reviewed values remain auditable.
7. A customer starts a web chat, it routes through the same queue, and an agent resolves and wraps it up.
8. Supervisor and client-viewer dashboards update with correctly scoped metrics.
9. CSV and PDF client reports reproduce the filtered results.
10. English, Hindi, Marathi, and code-switched fixtures pass the documented language checks.
11. Strict-local mode passes with outbound customer-content egress blocked.
12. The cost report separates telephony, transcription, inference, storage, and human-review cost per interaction.

## Current Acceptance Status

The 1-3 seat deterministic pilot path passes all twelve acceptance areas through automated API, Chrome, Electron, packaged-executable, Docker, privacy, and export checks. Where external authority would be required, the accepted evidence-backed substitute is explicit:

- Voice uses the deterministic local test trunk and synchronized English two-speaker fixture, not a live carrier.
- The second isolated agent is verified at the authorization/realtime layer; a 700-seat load claim is intentionally deferred.
- English, Hindi, Marathi, and code switching are exercised in the digital workflow; only English is claimed for synchronized voice evidence.
- Human-review cost has a distinct ledger category in the model, while the deterministic fixture currently generates telephony, transcription, inference, and storage events automatically.

See `docs/VERIFICATION.md` for exact commands, results, evidence files, and remaining boundaries.
