# Verification Record

Last verified: 2026-08-10 on Windows with Docker Desktop. This record applies to the current source and local evidence baseline; it is not a 700-seat or production-HA certification.

## Final acceptance

| Layer | Result | Current evidence |
|---|---|---|
| API | Pass | 18 tests passed; one upstream Starlette/httpx deprecation warning. |
| Frontend | Pass | TypeScript and Vite production build passed; 1,835 modules transformed. |
| Clean evidence baseline | Pass | 5 closed interactions: 4 licensed voice calls and 1 labelled transcript-channel replay; 5 provenance audits; 4 Groq QA evaluations; 0 actual-CSAT claims. |
| Browser E2E | Pass | Desktop 1600 px, mobile portal 375 px, customer widget 375 px; zero captured console/network failures; 5 evidence records and 4 Groq evaluations observed. |
| Electron controls | Pass | Exact chat claim/reply/wrap-up, inbound reject/accept, mute, unmute, hold, resume, transfer, hang-up, outbound start, and native 1426x779 fit. Queue-only simulations made no transcript/recording/AI claims. |
| Outbound SIP + AI | Pass | Electron 1001 -> Asterisk 2003 -> browser 1003; separate human speech tracks, two-party media, 4 role-correct live transcript segments, stored recording, Groq QA, wrap-up. |
| Inbound SIP + AI | Pass | Browser 1003 -> Asterisk 2101 -> Electron 1001; ringing queue, accept, two-party media, 4 role-correct live transcript segments, stored recording, Groq QA. |
| Durability | Pass | Hang-up returns without waiting for Groq; one background worker claims finalization; a 15-minute stale lock prevents duplicate evaluation under rate-limited processing; provider failures remain retryable. |
| Package | Pass | Unpacked executable and silently installed executable both logged in and passed native-window fit. |
| Installer | Pass | `Aperture CX Agent Setup 0.1.0.exe`, 101,773,464 bytes, SHA-256 `1AA9491A75F1BB765F6C9B4C947C5DB855C61E75A4601EDFA9BB318D0B935F97`. Authenticode status: `NotSigned`. |
| Startup launcher | Pass | `scripts/start_demo.ps1 -NoDesktop` inherited the Windows User Groq key, started the six required services, and reached API health. |

## Clean baseline semantics

- Source: Stanford/Gridspace HarperValleyBank human-performed simulated banking calls, CC BY 4.0.
- Boundary: these are published simulated calls, not production customer calls.
- Transformations: original caller and agent tracks are transcribed separately by `whisper-large-v3`; caller-left/agent-right stereo is built without speech synthesis; `openai/gpt-oss-20b` produces guidance, summaries, predicted risk, and one schema-validated answer per rubric question.
- Visible result: 4 voice records, 1 transcript-channel replay, average automatic QA 84, range 40-99, average predicted dissatisfaction risk 10, and estimated measured usage cost INR 1.57.
- Actual CSAT count is zero. Published partner ratings stay in provenance metadata and are not mapped to CSAT.
- The score of 40 is retained: Groq ASR heard a branch-hours answer that conflicts with published task metadata. This is a useful real model/data finding, not corrected demo data.

## Commands run

```powershell
docker run --rm -v "C:\CS\Agency\BPO-Demo\services\platform-api\tests:/app/tests:ro" bpo-demo-platform-api pytest -q

Set-Location C:\CS\Agency\BPO-Demo\apps\console
npm run build
npm run test:e2e:web
npm run test:e2e:electron
npm run test:e2e:sip
npm run electron:pack
npm run test:e2e:packaged
npx electron-builder --win nsis --prepackaged release\win-unpacked
```

The strict SIP test intentionally used separate CC-BY human caller/agent files as fake microphone inputs while exercising actual WebRTC/SIP media. This makes the test repeatable without claiming a live human was present during automation. It validated outbound and inbound media independently before the clean baseline was restored.

## AI choice and measured pricing basis

- `whisper-large-v3` remains the accuracy-first multilingual ASR model. Groq currently lists it at USD 0.111 per audio hour and explicitly recommends it for error-sensitive multilingual work.
- `openai/gpt-oss-20b` is used for live guidance and QA because it supports JSON Schema output, has a 131,072-token context window, and is priced at USD 0.075/M uncached input tokens and USD 0.30/M output tokens.
- Cost values in the UI are estimates derived from measured audio seconds/model tokens and configured USD-to-INR conversion. They are not invoices.
- Groq rate limits were observed during the final SIP run. Bounded retry succeeded; the desktop remained responsive because final QA is asynchronous.

Official model sources: https://console.groq.com/docs/model/whisper-large-v3, https://console.groq.com/docs/model/openai/gpt-oss-20b, and https://groq.com/pricing.

## Honest limits

- No PSTN carrier trunk, Indian number/KYC/DLT onboarding, or trunk failover was exercised.
- No 700-seat load, HA, failover, recovery-time, or disaster-recovery certification was performed.
- The clean licensed call set is English. Hindi, Marathi, and Hinglish product paths exist, but no equally strong multilingual human call corpus is included in the visible baseline. Marathi remains review-required.
- No predictive/progressive dialer, workforce scheduling, screen recording, native WhatsApp, or autonomous voice bot is claimed.
- The installer is not code-signed and uses Electron's default icon.
- External mode sends audio/transcript context to Groq. It is not fully local/private AI.
