export type Role = "admin" | "supervisor" | "qa_reviewer" | "agent" | "client_viewer";
export type ConversationStatus = "queued" | "active" | "wrap_up" | "closed" | "failed";

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  display_name: string;
  role: Role;
}

export interface Conversation {
  id: string;
  channel: "voice" | "web_chat" | "email" | "whatsapp";
  status: ConversationStatus;
  direction: "inbound" | "outbound";
  assigned_user_id: string | null;
  language: string;
  disposition: string | null;
  summary: string | null;
  started_at: string;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  sender_type: "customer" | "agent" | "system";
  sender_user_id: string | null;
  content: string;
  sequence: number;
  created_at: string;
}

export interface AgentRow {
  id: string;
  display_name: string;
  email: string;
  status: string;
  current_conversation_id: string | null;
}

export interface VoiceSession {
  conversation_id: string;
  provider: string;
  provider_call_id: string;
  state: "ringing" | "active" | "held" | "ended" | "rejected";
  muted: boolean;
  held: boolean;
  transfer_target: string | null;
}

export interface TranscriptSegment {
  id: string;
  speaker: "agent" | "customer";
  text: string;
  start_ms: number;
  end_ms: number;
  language: string;
  confidence: number;
}

export interface AssistEvent {
  id: string;
  event_type: string;
  title: string;
  content: string;
  evidence_start_ms: number | null;
  evidence_end_ms: number | null;
  metadata: Record<string, unknown>;
}

export interface QAEvaluation {
  id: string;
  conversation_id: string;
  automatic_score: number;
  reviewed_score: number | null;
  effective_score: number;
  fatal_triggered: boolean;
  status: string;
  provider: string;
  model: string;
  summary: string;
  created_at: string;
}
