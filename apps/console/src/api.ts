import type { AgentRow, ChatMessage, Conversation, User } from "./types";

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
  startChat: (customerName: string, initialMessage: string, language: string) => request<{ conversation_id: string; session_token: string; status: string }>("/public/chat/start", { method: "POST", body: JSON.stringify({ tenant_slug: "aperture-pilot", widget_key: import.meta.env.VITE_CHAT_WIDGET_KEY || "pilot-widget-key-change-me", customer_name: customerName, language, initial_message: initialMessage }) }),
  customerMessages: (id: string, session: string) => request<ChatMessage[]>(`/public/chat/${id}/messages`, { headers: { "X-Chat-Session": session } }),
  sendCustomerMessage: (id: string, session: string, content: string) => request<ChatMessage>(`/public/chat/${id}/messages`, { method: "POST", headers: { "X-Chat-Session": session }, body: JSON.stringify({ content }) }),
};

export function connectRealtime(token: string, onEvent: (event: Record<string, unknown>) => void): WebSocket {
  const socketBase = API_BASE.startsWith("http")
    ? API_BASE.replace(/^http/, "ws")
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${API_BASE}`;
  const ws = new WebSocket(`${socketBase}/realtime`, ["bpo-realtime", token]);
  ws.onmessage = (event) => onEvent(JSON.parse(event.data));
  return ws;
}
