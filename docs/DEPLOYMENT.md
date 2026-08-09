# Deployment and Carrier Onboarding

Last updated: 2026-08-10.

## What can go live without another vendor

The unified portal, Electron desktop, Postgres data model, durable worker, web chat, reporting, default Groq processing, strict-local test fixtures, and same-host WebRTC/SIP calls all run in Docker plus the Windows desktop. This is suitable for a controlled 1-3 seat pilot on a private network after secrets, TLS, backups, retention, recording consent, and client configuration are completed.

It is not a public production deployment or a 700-seat certification. There is no purchased DID, PSTN route, carrier SLA, HA cluster, disaster-recovery proof, or load result in this repository.

## AI modes

### Groq external

Default. Provide `GROQ_API_KEY` through the untracked `.env` before startup. The API and worker fail visibly instead of silently substituting deterministic output when the credential is absent. New tenants start in external mode. The current model choices are:

| Job | Model | Why |
|---|---|---|
| Near-realtime and final ASR | `whisper-large-v3` | Best measured multilingual accuracy in this repo; the small latency difference versus Turbo was immaterial for 15-second chunks. |
| Guidance, summaries, risk, and QA | `openai/gpt-oss-20b` | Strict JSON schema support, low measured latency, large context, and lower cost than 120B for this workflow. |

The desktop records mixed call media, uploads standalone 15-second WebM chunks for near-realtime assist, then uploads the complete recording before hangup. Groq word timestamps feed transcript evidence. Configured scripts and the top lexical knowledge matches are passed to strict-schema analysis. The final durable job writes summary, assists, predicted risk, evidence-linked QA, provider/model/request metadata, and cost events. Provider errors fail visibly and remain retryable; they do not silently create a successful score.

Groq says API customer data may be retained for up to 30 days by default unless an eligible Zero Data Retention arrangement applies. Confirm the client policy and Groq account configuration before real customer audio is enabled. `USD_TO_INR` is a configurable accounting assumption, not a live exchange-rate feed.

### Strict local deterministic mode

Optional fallback/test mode. Customer-content network egress is false, and an automated test blocks outbound sockets while voice finalization succeeds. This repeatable lane uses known fixtures and deterministic rules; it is not a claim of local generative AI. An admin must deliberately switch to it when client policy prohibits the default Groq route.

## Carrier-free SIP proof

The checked-in Asterisk configuration exposes WebSocket SIP endpoints 1001 and 1003. Extension 2003 routes 1001 to 1003. The automated test registers both, creates real WebRTC peer connections, confirms an active Asterisk channel, and exercises mute, hold, resume, and hangup. It proves media/control integration without claiming PSTN.

## What is required for real inbound/outbound phone numbers

The BPO or client must supply and authorize:

1. A licensed SIP trunk/carrier account, DID inventory, destination regions, caller IDs, concurrent-call requirement, and credentials or IP allowlist.
2. India telecom/KYC eligibility and the lawful outbound-calling category. The carrier must confirm applicable DLT/UCC, CLI, recording, consent, and data-location obligations for the exact campaign. This repository does not decide legal eligibility.
3. Carrier SIP details: registrar/proxy, transport, authentication, codecs, DTMF, number format, inbound route, outbound route, failover targets, and rate limits.
4. Network controls: static public IP or SBC, firewall/NAT rules, TLS/SRTP certificates, WSS for remote desktops, and restricted Asterisk management ports.
5. Business configuration: queues, schedules, overflow, dispositions, scripts, knowledge, QA rubric, retention, redaction, and authorized users.

Implementation then consists of a named Asterisk trunk object, inbound DID-to-queue rules, an outbound dial pattern that routes through that trunk, carrier failure codes surfaced to the API, and a controlled live-number acceptance test. No carrier-specific credentials belong in Git.

## Production gates

- Replace every seeded password/JWT/SIP/ARI secret and disable demo seeding.
- Put API, portal, WSS, and SIP behind trusted TLS certificates; remove public exposure of Postgres and management endpoints.
- Implement organization SSO/MFA, secret management, backup/restore drills, retention deletion, monitoring, alerting, and incident procedures.
- Obtain recording notices/consent and approve the cloud-AI data path per campaign.
- Run security review, dependency scanning, abuse/rate-limit tests, carrier failover tests, and representative multilingual human QA.
- Load-test the exact target concurrency and retention profile. For 700 seats, add horizontal API/workers, HA Postgres, shared object storage, multiple Asterisk/SBC nodes, routing/failover, observability, and disaster recovery before making a readiness claim.

## Useful commands

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps

$env:AGENT_UI_PORT='18082'
docker compose --profile legacy-ui up -d --build agent-ui

Set-Location apps\console
npm run test:e2e:sip
```

Official provider references: [Groq speech-to-text](https://console.groq.com/docs/speech-to-text), [Groq structured outputs](https://console.groq.com/docs/structured-outputs), [Groq data controls](https://console.groq.com/docs/your-data), and [Asterisk WebRTC configuration](https://docs.asterisk.org/Configuration/WebRTC/Configuring-Asterisk-for-WebRTC-Clients/).
