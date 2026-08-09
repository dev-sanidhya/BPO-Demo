import type { AgentRow, AssistEvent, ChatMessage, Conversation, QAEvaluation, TranscriptSegment, User, VoiceSession } from "./types";

const API_BASE = window.platformRuntime?.apiBase || import.meta.env.VITE_PLATFORM_API_URL || "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new ApiError(response.status, body.detail || "Request failed");
  }
  return response.json();
}

export const api = {
  login: (email: string, password: string) => request<{ access_token: string; user: User }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  conversations: (token: string) => request<Conversation[]>("/conversations", {}, token),
  queued: (token: string) => request<Conversation[]>("/work/queued", {}, token),
  agents: (token: string) => request<AgentRow[]>("/agents", {}, token),
  summary: (token: string) => request<{ conversations: Record<string, number>; agents: Record<string, number> }>("/dashboard/summary", {}, token),
  messages: (token: string, id: string) => request<ChatMessage[]>(`/conversations/${id}/messages`, {}, token),
  claim: (token: string, id: string) => request<Conversation>(`/conversations/${id}/claim`, { method: "POST" }, token),
  sendMessage: (token: string, id: string, content: string) => request<ChatMessage>(`/conversations/${id}/messages`, { method: "POST", body: JSON.stringify({ content }) }, token),
  presence: (token: string, status: string) => request(`/agents/me/presence`, { method: "PUT", body: JSON.stringify({ status }) }, token),
  wrapUp: (token: string, id: string, disposition: string, summary: string) => request<Conversation>(`/conversations/${id}/wrap-up`, { method: "POST", body: JSON.stringify({ disposition, summary }) }, token),
  dialVoice: (token: string, phone: string, customerName: string, language: string) => request<{ conversation: Conversation; session: VoiceSession }>("/voice/calls/dial", { method: "POST", body: JSON.stringify({ phone, customer_name: customerName, language }) }, token),
  voiceCall: (token: string, id: string) => request<{ conversation: Conversation; session: VoiceSession }>(`/voice/calls/${id}`, {}, token),
  voiceControl: (token: string, id: string, action: string, target?: string) => request<VoiceSession>(`/voice/calls/${id}/control`, { method: "POST", body: JSON.stringify({ action, target }) }, token),
  rejectVoice: (token: string, id: string) => request<VoiceSession>(`/voice/calls/${id}/reject`, { method: "POST" }, token),
  transcript: (token: string, id: string) => request<TranscriptSegment[]>(`/conversations/${id}/transcript`, {}, token),
  assist: (token: string, id: string) => request<AssistEvent[]>(`/conversations/${id}/assist`, {}, token),
  recording: async (token: string, id: string) => { const response = await fetch(`${API_BASE}/conversations/${id}/recording`, { headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) throw new ApiError(response.status, "Recording unavailable"); return response.blob(); },
  uploadRecording: async (token: string, id: string, blob: Blob, durationMs: number) => { const form = new FormData(); form.append("file", blob, "browser-call.webm"); form.append("duration_ms", String(durationMs)); const response = await fetch(`${API_BASE}/voice/calls/${id}/recording`, { method: "PUT", headers: { Authorization: `Bearer ${token}` }, body: form }); if (!response.ok) { const body = await response.json().catch(() => ({ detail: "Recording upload failed" })); throw new ApiError(response.status, body.detail); } return response.json(); },
  ingestVoiceChunk: async (token: string, id: string, blob: Blob, startMs: number) => { const form = new FormData(); form.append("file", blob, "live-chunk.webm"); form.append("speaker", "unknown"); form.append("start_ms", String(startMs)); const response = await fetch(`${API_BASE}/voice/calls/${id}/audio-chunks`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form }); if (!response.ok) { const body = await response.json().catch(() => ({ detail: "Live AI failed" })); throw new ApiError(response.status, body.detail); } return response.json(); },
  qaEvaluations: (token: string) => request<QAEvaluation[]>("/qa/evaluations", {}, token),
  qaDetail: (token: string, id: string) => request<Record<string, unknown>>(`/qa/evaluations/${id}`, {}, token),
  reviewQA: (token: string, id: string, reviewedScore: number, reason: string) => request(`/qa/evaluations/${id}/reviews`, { method: "POST", body: JSON.stringify({ reviewed_score: reviewedScore, reason }) }, token),
  configuration: (token: string) => request<Record<string, unknown>>("/configuration", {}, token),
  diagnostics: (token: string) => request<Record<string, unknown>>("/diagnostics", {}, token),
  updatePrivacy: (token: string, aiMode: string) => request("/configuration/privacy", { method: "PUT", body: JSON.stringify({ ai_mode: aiMode }) }, token),
  updatePilot: (token: string, payload: Record<string, unknown>) => request("/configuration/pilot", { method: "PUT", body: JSON.stringify(payload) }, token),
  createUser: (token: string, payload: Record<string, unknown>) => request<User>("/users", { method: "POST", body: JSON.stringify(payload) }, token),
  reportSummary: (token: string, query = "") => request<Record<string, unknown>>(`/reports/summary${query}`, {}, token),
  reportCosts: (token: string) => request<Record<string, unknown>>("/reports/costs", {}, token),
  downloadReport: async (token: string, format: "csv" | "pdf", query = "") => { const response = await fetch(`${API_BASE}/reports/export.${format}${query}`, { headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) throw new ApiError(response.status, "Report export failed"); return response.blob(); },
  startChat: (customerName: string, initialMessage: string, language: string) => request<{ conversation_id: string; session_token: string; status: string }>("/public/chat/start", { method: "POST", body: JSON.stringify({ tenant_slug: "aperture-pilot", widget_key: import.meta.env.VITE_CHAT_WIDGET_KEY || "pilot-widget-key-change-me", customer_name: customerName, language, initial_message: initialMessage }) }),
  customerMessages: (id: string, session: string) => request<ChatMessage[]>(`/public/chat/${id}/messages`, { headers: { "X-Chat-Session": session } }),
  sendCustomerMessage: (id: string, session: string, content: string) => request<ChatMessage>(`/public/chat/${id}/messages`, { method: "POST", headers: { "X-Chat-Session": session }, body: JSON.stringify({ content }) }),
  customerStatus: (id: string, session: string) => request<{ status: string; actual_csat: number | null }>(`/public/chat/${id}/status`, { headers: { "X-Chat-Session": session } }),
  submitSurvey: (id: string, session: string, csat: number) => request<{ actual_csat: number; source: string }>(`/public/chat/${id}/survey`, { method: "POST", headers: { "X-Chat-Session": session }, body: JSON.stringify({ csat }) }),
};

export function connectRealtime(token: string, onEvent: (event: Record<string, unknown>) => void): WebSocket {
  const socketBase = API_BASE.startsWith("http")
    ? API_BASE.replace(/^http/, "ws")
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${API_BASE}`;
  const ws = new WebSocket(`${socketBase}/realtime`, ["bpo-realtime", token]);
  ws.onmessage = (event) => onEvent(JSON.parse(event.data));
  return ws;
}
