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

