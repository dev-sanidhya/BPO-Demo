# Aperture CX Demo Guide

This guide runs the verified AI-first local pilot. It uses real two-party WebRTC/SIP media through Asterisk and Groq for live transcription, guidance, post-call QA, summaries, predicted dissatisfaction risk, and measured AI usage. It does not place a PSTN/mobile-network call.

## Start everything

Prerequisites: Docker Desktop is running, the Windows User environment contains `GROQ_API_KEY`, and either the installer has been run or the packaged desktop exists under `apps\console\release\win-unpacked`.

From PowerShell:

```powershell
Set-Location C:\CS\Agency\BPO-Demo
powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
```

The script opens the agent desktop and starts:

- Operations portal: http://127.0.0.1:18081
- Browser customer/SIP endpoint: http://127.0.0.1:18082/?ext=1003&pass=changeme1003&assist=0&target=2101
- API health: http://127.0.0.1:18080/health

Local demo password: `PilotTest123!`

| View | Login |
|---|---|
| Agent desktop | `agent1@pilot.example` |
| Supervisor | `supervisor@pilot.example` |
| QA reviewer | `qa@pilot.example` if provisioned |
| Admin | `admin@pilot.example` |
| Restricted client portal | `client@pilot.example` |

## Outbound talkable call

1. Open the customer/SIP endpoint in Chrome and allow microphone access. Wait for `SIP: registered as 1003`.
2. Sign into the desktop as Agent 1. Confirm the top bar shows `SIP 1001`.
3. Enter `2003` as the customer phone and click **Call extension**.
4. Speak in both Chrome and Electron. Use mute, hold/resume, and transfer if desired.
5. Watch speaker-attributed transcript and guidance appear as audio chunks complete. Groq latency/rate limits can make guidance arrive after a chunk rather than word-by-word.
6. Hang up. The desktop ends immediately; the durable worker finishes QA and reporting in the background. Complete wrap-up when ready.

## Inbound talkable call

1. Keep the Electron agent signed in and the Chrome customer endpoint registered.
2. In Chrome, click **Call**. Its target is `2101`, which Asterisk routes to agent extension `1001`.
3. The inbound interaction appears in the desktop queue. Click **Accept** and speak normally from both windows.
4. Hang up and complete wrap-up. The same recording, transcription, QA, risk, cost, and reporting pipeline runs.

Use headphones to prevent acoustic echo when both endpoints are on one laptop. For the cleanest demo, use a second laptop or phone browser on the same network after replacing the demo SIP passwords and exposing the host safely.

## Walk through the platform

1. **Supervisor overview:** shows only the current five-record evidence dataset by default.
2. **Conversations:** open a call, play its stereo recording, inspect speaker-attributed Groq transcript, assists, QA evidence, and the provenance card.
3. **Quality:** compare automatic scores and evidence spans. A review creates a separate reviewed score; it does not overwrite the model score.
4. **Reports:** filter by channel/agent/campaign, download CSV/PDF, and show actual CSAT separately from predicted risk. The clean evidence dataset intentionally has no actual CSAT.
5. **Costs:** values are measured usage estimates from audio seconds, model tokens, storage bytes, and the configured INR conversion. They are not provider invoices.
6. **Client login:** demonstrates campaign-scoped read-only access.
7. **Customer widget:** open http://127.0.0.1:18081/?widget=1 to demonstrate a native web-chat session and real survey collection. Do this after showing the clean baseline because a new session correctly creates new live records.

## What the default records are

The four voice records are human-performed simulated banking calls from Stanford/Gridspace HarperValleyBank, licensed CC BY 4.0. They are not production customer calls. Original caller and agent tracks are retained separately, transcribed by Groq, combined as caller-left/agent-right stereo, and scored against a corpus-derived rubric. The fifth record maps one published human transcript into a digital timeline to prove the unified channel UI; it is labelled as a replay, not as a native historical chat.

Every visible record has an in-product provenance card with source, license, hashes, boundaries, and transformations. Published partner ratings are source metadata only and are never presented as CSAT.

## Honest limits

- Real local SIP/WebRTC calls work; PSTN/SIM/mobile-number calling requires a carrier SIP trunk and client KYC/DLT configuration.
- English is verified on the current human call set. Hindi, Marathi, and Hinglish selectors and Groq processing paths exist, but this clean licensed call set is English. Marathi remains review-required based on the existing small benchmark.
- The product is not yet certified for 700 concurrent seats, HA/failover, predictive dialing, workforce management, screen recording, native WhatsApp, or code-signed distribution.
- Groq is the default AI route and sends audio/transcript context to Groq. Do not claim fully local/private AI in this mode.

## Stop the stack

```powershell
Set-Location C:\CS\Agency\BPO-Demo
docker compose --profile legacy-ui down
```

The database and recordings remain in Docker volumes. `down` does not erase them; do not add `-v` unless you intentionally want to delete local demo data.
