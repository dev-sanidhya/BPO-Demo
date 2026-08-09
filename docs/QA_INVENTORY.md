# UI QA inventory

This checklist is the minimum sign-off surface for the shared portal and Electron agent desktop.

| Claim or control | Functional check | Visual state / evidence |
|---|---|---|
| Packaged desktop starts against the on-prem API | Launch Electron, authenticate an agent with normal form input | Login and agent workspace screenshots at the native launch size |
| Customer chat and agent queue are one workflow | Start public chat, accept it in Electron, reply, confirm reply from customer session | Populated work queue and active conversation |
| Wrap-up changes operational state | Resolve in Electron, confirm conversation is closed through the API | Empty/caught-up workspace after resolve |
| Supervisor sees live operations | Authenticate supervisor and verify queue/agent metrics | 1600x900 dashboard, including dense interaction table |
| Customer widget works on desktop and mobile | Start a conversation and exchange messages | 430px widget plus 375px mobile viewport |
| Presence control works | Cycle available -> break -> available and verify persisted state | Header control in each state |
| Authentication failure is helpful | Submit an incorrect password | Visible inline error; no broken layout |
| Responsive layout remains usable | Exercise login/widget/portal at 375px width | No horizontal clipping or obscured primary controls |

Exploratory checks: transient customer polling failure must not crash the widget; a client-viewer login must not request the supervisor-only live-floor endpoint.

