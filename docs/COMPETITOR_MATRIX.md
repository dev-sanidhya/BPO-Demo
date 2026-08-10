# Competitor Capability Matrix

Research date: 2026-08-09. Sources are official vendor product pages or documentation. Vendor claims are recorded as claims, not independently verified benchmarks.

Pricing rechecked: 2026-08-10. Public list prices are reference points, not India enterprise quotes. Genesys currently lists named-user annual plans at USD 75/115/155/240 per user-month for CX 1/2/3/4, with usage and AI-token conditions. Exotel publicly lists smaller business-phone bundles at INR 9,999, INR 19,999, and INR 49,499 with different validity, credits, numbers, and agent limits; its enterprise contact-center and AI pricing remains sales-led. These are not directly equivalent to Aperture's implementation-plus-SaaS pilot.

## Current Market Bar

| Vendor | Officially presented capabilities relevant to this build | Product implication |
|---|---|---|
| Genesys Cloud CX | Voice and digital channels, omnichannel routing, outbound campaigns, recording, QA/compliance, knowledge, speech/text analytics, Agent Copilot, reporting, exports, surveys, and workforce capabilities. | Routing, recording, digital continuity, QA, knowledge, and actionable reporting are table stakes. |
| NICE CXone | Omnichannel interaction analytics, quality management, automated interaction selection, calibration, routing, and workforce engagement. | A credible QA product needs calibration and supervisor workflows, not only LLM scores. |
| Five9 | Agent desktop, inbound/outbound, ACD/IVR/dialer, recording, voice/chat/email/SMS/social, live transcription, assist, knowledge, summaries, QM, analytics, WFM, and workflow automation. | The unified desktop must cover practical contact handling and after-call work, not only show prompts. |
| Observe.AI | 100% conversation analysis, Auto QA, smart scripts, contextual alerts, knowledge, summarization, supervisor assist, simulation, and cross-channel case intelligence. | Guidance must be configurable and contextual; every metric should trace back to conversations. |
| Cresta | 100% AI quality evaluation, behavior-to-outcome analysis, realtime supervision/intervention, and multi-model architecture. | QA should connect behaviors to outcomes and enable live supervisor action over time. |
| Ameyo | On-prem/cloud/hybrid deployment; voice, email, webchat, SMS, mobile, social, WhatsApp; unified journey context; routing; and channel/agent/live reports. | This is the closest deployment and India-market table-stakes reference. On-prem alone is not differentiation. |
| Exotel | Realtime assist, knowledge, next-best actions, compliance guidance, after-call automation, omnichannel readiness, security, and masking. | Indian buyers can already buy cloud telephony plus assist; our privacy and ownership claims must be concrete. |

## Implemented Parity and Deliberate Gaps

| Market capability | Aperture CX status |
|---|---|
| Voice agent desktop and call controls | Implemented and proven over local Asterisk WebRTC; PSTN carrier onboarding remains external. |
| Live transcript, contextual knowledge, prompts, and checklists | Implemented with 15-second near-realtime Groq chunks plus strict-local deterministic fallback. |
| Automated summary and QA | Implemented with strict-schema output, timestamp evidence, immutable automatic score, review override, and durable retry. |
| Conversation analytics and exports | Implemented for voice and web chat with campaign/queue/agent filters, CSV/PDF, actual CSAT, predicted risk, and cost ledger. |
| Multilingual | English, Hindi, Marathi, and Hinglish lanes exist; Marathi is review-required based on measured ASR error. |
| Full CCaaS routing, WFM, predictive dialer, native WhatsApp/social, screen recording | Not implemented. Mature suites remain materially broader here. |
| Enterprise scale/HA/compliance certification | Not verified. No 700-seat claim. |

The differentiation is fit, not universal superiority: a buyer can inspect and own one deployable codebase spanning the desktop, telephony extension point, live assistance, evidence-linked QA, reporting, strict-local fallback, and transparent cost. Mature vendors offer much deeper carrier, workforce, channel, compliance, and scale operations.

## Credible Differentiation

This product should not claim broader feature superiority over mature enterprise suites. It should be better suited to the target buyer on these dimensions:

1. **Data custody:** a verifiable strict-local AI mode, not merely a locally hosted UI that sends audio to a cloud model.
2. **Integrated pilot economics:** 1-3 seats can exercise all four product pillars without enterprise minimum-seat commitments.
3. **India-language operations:** tested English, Hindi, Marathi, and code-switched workflows with client-specific vocabulary.
4. **Auditability:** QA conclusions link to exact transcript/audio evidence, rule versions, confidence, and reviewer history.
5. **Client configurability:** scripts, knowledge, QA forms, fatal compliance rules, reports, and data retention are configurable per BPO client/campaign.
6. **Transparent unit economics:** the platform measures its own AI, telephony, storage, and review cost per call so the buyer can compare AI-assisted QA with manual QA.
7. **Deployment ownership:** documented Docker/on-prem installation, exportable data, and no dependency on the incumbent dialer.

## Claims We Must Not Make Yet

- “Better than Genesys/NICE/Five9” without a defined buyer-specific comparison.
- “Omnichannel” before two real channels pass the unified workflow.
- “100% compliant” or “100% accurate.”
- “Fully on-prem/private” while Groq or another external provider receives customer content.
- “CSAT/DSAT” when only sentiment or predicted satisfaction risk was calculated.
- “700-seat ready” before capacity, high availability, failover, and recovery tests pass.
- “Production WhatsApp” without client-owned Meta onboarding and live verification.

## Primary Sources

- Genesys pricing and plan features: https://www.genesys.com/pricing
- Genesys quality assurance and monitoring: https://www.genesys.com/capabilities/quality-assurance-and-monitoring
- Genesys speech and text analytics: https://www.genesys.com/capabilities/speech-and-text-analytics
- Genesys reporting and analytics: https://www.genesys.com/capabilities/reporting-analytics
- Genesys workforce engagement management: https://www.genesys.com/en-gb/capabilities/wem-workforce-engagement-management
- Five9 pricing and bundle capabilities: https://www.five9.com/products/pricing
- Five9 platform capabilities: https://www.five9.com/products-solutions
- Five9 agent assist: https://www.five9.com/en-ca/products/capabilities/agent-assist
- Observe.AI interaction intelligence: https://www.observe.ai/platform/interaction-intelligence
- Observe.AI realtime agent assist: https://www.observe.ai/real-time/agent-assist
- Cresta quality management: https://cresta.com/cresta-qm
- Cresta agent operations center: https://cresta.com/agent-operations-center
- Ameyo omnichannel/on-prem offering: https://www.ameyo.com/product/omni/
- Ameyo omnichannel features: https://www.ameyo.com/product/omni/features
- Exotel agent assist: https://exotel.com/products/agent-assist/
- Exotel public plans: https://exotel.com/pricing/ and https://exotel.com/pricing/business-phone-system/
