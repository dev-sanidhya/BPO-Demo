import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, AudioWaveform as Waveform, BarChart3, BookOpen, CheckCircle2, ChevronRight, CircleUserRound,
  ClipboardCheck, Clock3, Headphones, Inbox, LayoutDashboard, LockKeyhole,
  LogOut, MessageSquareText, Phone, Search, Send, Settings, ShieldCheck, Sparkles,
  UsersRound,
} from "lucide-react";
import { api, ApiError, connectRealtime } from "./api";
import type { AgentRow, ChatMessage, Conversation, User } from "./types";

const roleLabels: Record<string, string> = {
  admin: "Administrator", supervisor: "Floor supervisor", qa_reviewer: "Quality reviewer",
  agent: "Agent", client_viewer: "Client viewer",
};

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function Login({ onLogin }: { onLogin: (token: string, user: User) => void }) {
  const [email, setEmail] = useState(window.platformRuntime?.desktop ? "agent1@pilot.example" : "supervisor@pilot.example");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true); setError("");
    try {
      const result = await api.login(email, password);
      onLogin(result.access_token, result.user);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to reach the on-prem server.");
    } finally { setLoading(false); }
  }

  return <main className="login-shell">
    <section className="login-story">
      <div className="brand-mark"><Waveform size={21} /> APERTURE CX</div>
      <div className="story-copy">
        <div className="eyebrow"><span /> PRIVATE CONTACT CENTER INTELLIGENCE</div>
        <h1>Every conversation.<br /><em>One operating system.</em></h1>
        <p>Voice, digital support, live agent guidance, quality automation and client-ready intelligence, running inside your infrastructure.</p>
        <div className="trust-row"><span><ShieldCheck size={18} /> On-premise</span><span><LockKeyhole size={18} /> Local AI ready</span><span><Activity size={18} /> Live operations</span></div>
      </div>
      <div className="story-signal"><div className="pulse-ring"><Waveform size={28} /></div><div><strong>Platform online</strong><span>Private workspace · India South</span></div></div>
    </section>
    <section className="login-panel">
      <form onSubmit={submit} className="login-card">
        <div className="mobile-brand"><Waveform size={20} /> APERTURE CX</div>
        <div><span className="section-kicker">SECURE WORKSPACE</span><h2>Welcome back</h2><p>Sign in to your assigned operations environment.</p></div>
        <label>Work email<input aria-label="Work email" value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="username" /></label>
        <label>Password<input aria-label="Password" value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" placeholder="Enter your password" /></label>
        {error && <div className="form-error">{error}</div>}
        <button className="primary-button" disabled={loading}>{loading ? "Connecting…" : "Enter workspace"}<ChevronRight size={18} /></button>
        <div className="login-foot"><ShieldCheck size={16} /><span>Your session is authenticated against the local deployment.</span></div>
      </form>
    </section>
  </main>;
}

function Sidebar({ user, page, onPage, onLogout }: { user: User; page: string; onPage: (value: string) => void; onLogout: () => void }) {
  const agent = user.role === "agent";
  const items = agent
    ? [["workspace", Headphones, "Workspace"], ["inbox", Inbox, "Queue"], ["knowledge", BookOpen, "Knowledge"]]
    : [["overview", LayoutDashboard, "Overview"], ["conversations", MessageSquareText, "Conversations"], ["quality", ClipboardCheck, "Quality"], ["team", UsersRound, "Live floor"], ["reports", BarChart3, "Reports"]];
  return <aside className="sidebar">
    <div className="sidebar-brand"><div><Waveform size={20} /></div><span>APERTURE <b>CX</b></span></div>
    <nav>{items.map(([id, Icon, label]) => <button key={id as string} onClick={() => onPage(id as string)} className={page === id ? "active" : ""}><Icon size={18} /><span>{label as string}</span></button>)}</nav>
    <div className="sidebar-bottom">
      {user.role === "admin" && <button><Settings size={18} /><span>Settings</span></button>}
      <div className="identity"><div className="avatar">{user.display_name.split(" ").map((part) => part[0]).slice(0, 2).join("")}</div><div><strong>{user.display_name}</strong><span>{roleLabels[user.role]}</span></div><button aria-label="Log out" onClick={onLogout}><LogOut size={17} /></button></div>
    </div>
  </aside>;
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill ${status}`}><i />{status.replace("_", " ")}</span>;
}

function SupervisorView({ token, user, conversations, agents, summary, refresh }: { token: string; user: User; conversations: Conversation[]; agents: AgentRow[]; summary: { conversations: Record<string, number>; agents: Record<string, number> } | null; refresh: () => void }) {
  const active = summary?.conversations.active || 0;
  const queued = summary?.conversations.queued || 0;
  const closed = summary?.conversations.closed || 0;
  const available = summary?.agents.available || 0;
  return <div className="page-content">
    <header className="page-header"><div><span className="section-kicker">OPERATIONS COMMAND</span><h1>Good afternoon, {user.display_name.split(" ")[0]}</h1><p>Live performance across your contact centre.</p></div><div className="header-actions"><button className="ghost-button"><Search size={17} /> Search</button><button className="live-button"><i /> Live</button></div></header>
    <section className="metric-grid">
      <article><div className="metric-icon emerald"><Phone size={20} /></div><div><span>Active interactions</span><strong>{active}</strong><small><b>Live</b> across voice + chat</small></div></article>
      <article><div className="metric-icon amber"><Clock3 size={20} /></div><div><span>Waiting in queue</span><strong>{queued}</strong><small>Oldest shown first</small></div></article>
      <article><div className="metric-icon blue"><UsersRound size={20} /></div><div><span>Agents available</span><strong>{available}<em> / {agents.length}</em></strong><small>Current floor state</small></div></article>
      <article><div className="metric-icon violet"><CheckCircle2 size={20} /></div><div><span>Resolved</span><strong>{closed}</strong><small>Current pilot dataset</small></div></article>
    </section>
    <section className="dashboard-grid">
      <article className="panel interaction-panel">
        <div className="panel-head"><div><h3>Live interactions</h3><p>Voice and digital work in one queue</p></div><button onClick={refresh}>Refresh</button></div>
        <div className="table-wrap"><table><thead><tr><th>Channel</th><th>Language</th><th>Status</th><th>Started</th></tr></thead><tbody>
          {conversations.slice(0, 8).map((conversation) => <tr key={conversation.id}><td><div className="channel-cell">{conversation.channel === "voice" ? <Phone size={16} /> : <MessageSquareText size={16} />}<span>{conversation.channel.replace("_", " ")}</span></div></td><td>{conversation.language.toUpperCase()}</td><td><StatusPill status={conversation.status} /></td><td>{formatTime(conversation.started_at)}</td></tr>)}
          {!conversations.length && <tr><td colSpan={4} className="empty-cell">No interactions yet. The live queue is ready.</td></tr>}
        </tbody></table></div>
      </article>
      <article className="panel floor-panel"><div className="panel-head"><div><h3>Live floor</h3><p>Availability and current load</p></div><UsersRound size={19} /></div><div className="agent-list">
        {agents.map((agent) => <div className="agent-row" key={agent.id}><div className="avatar small">{agent.display_name.split(" ").map((x) => x[0]).join("").slice(0, 2)}</div><div><strong>{agent.display_name}</strong><span>{agent.current_conversation_id ? "Handling interaction" : "No active work"}</span></div><StatusPill status={agent.status} /></div>)}
      </div></article>
    </section>
    <section className="insight-strip"><div className="insight-icon"><Sparkles size={20} /></div><div><span>OPERATIONS SIGNAL</span><strong>{queued ? `${queued} conversation${queued > 1 ? "s" : ""} waiting for an agent.` : "No customer is waiting right now."}</strong><p>Signals are computed from the local operational store, not a third-party dashboard.</p></div><ChevronRight size={20} /></section>
  </div>;
}

function AgentView({ token, user, assigned, queued, onRefresh }: { token: string; user: User; assigned: Conversation[]; queued: Conversation[]; onRefresh: () => void }) {
  const [selectedId, setSelectedId] = useState<string | null>(assigned.find((item) => item.status === "active")?.id || null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [presence, setPresence] = useState("available");
  const [error, setError] = useState("");
  const selected = assigned.find((item) => item.id === selectedId);

  const loadMessages = useCallback(async () => {
    if (!selectedId) { setMessages([]); return; }
    try { setMessages(await api.messages(token, selectedId)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load messages"); }
  }, [selectedId, token]);
  useEffect(() => { void loadMessages(); }, [loadMessages]);

  async function claim(id: string) { await api.claim(token, id); onRefresh(); setSelectedId(id); }
  async function send(event: FormEvent) { event.preventDefault(); if (!selectedId || !draft.trim()) return; await api.sendMessage(token, selectedId, draft.trim()); setDraft(""); await loadMessages(); }
  async function changePresence(value: string) { setPresence(value); await api.presence(token, value); }
  async function resolve() { if (!selectedId) return; await api.wrapUp(token, selectedId, "resolved", "Customer request resolved during the interaction."); setSelectedId(null); onRefresh(); }

  return <div className="agent-shell">
    <header className="agent-topbar"><div><span className="section-kicker">AGENT WORKSPACE</span><h1>{user.display_name}</h1></div><label className="presence-control"><i className={presence} /><select aria-label="Agent status" value={presence} onChange={(e) => void changePresence(e.target.value)}><option value="available">Available</option><option value="break">On break</option><option value="offline">Offline</option></select></label></header>
    <div className="agent-columns">
      <section className="work-list"><div className="work-list-head"><div><h3>My work</h3><span>{assigned.length} assigned</span></div><button onClick={onRefresh}><Activity size={16} /></button></div>
        {assigned.map((item) => <button key={item.id} onClick={() => setSelectedId(item.id)} className={`work-item ${selectedId === item.id ? "selected" : ""}`}><div className={`channel-badge ${item.channel}`}>{item.channel === "voice" ? <Phone size={16} /> : <MessageSquareText size={16} />}</div><div><strong>{item.channel === "web_chat" ? "Digital customer" : "Voice customer"}</strong><span>{item.language.toUpperCase()} · {formatTime(item.started_at)}</span></div><StatusPill status={item.status} /></button>)}
        <div className="queue-divider"><span>AVAILABLE QUEUE</span><b>{queued.length}</b></div>
        {queued.map((item) => <div key={item.id} className="queue-item"><div><MessageSquareText size={16} /><span><strong>New web chat</strong><small>{item.language.toUpperCase()} · waiting</small></span></div><button onClick={() => void claim(item.id)}>Accept</button></div>)}
        {!assigned.length && !queued.length && <div className="empty-state"><Inbox size={28} /><strong>You're caught up</strong><span>New work will appear here.</span></div>}
      </section>
      <section className="conversation-panel">
        {selected ? <><div className="conversation-head"><div><div className={`channel-badge ${selected.channel}`}><MessageSquareText size={17} /></div><div><strong>Customer conversation</strong><span>{selected.language.toUpperCase()} · Secure session</span></div></div><button className="resolve-button" onClick={() => void resolve()}><CheckCircle2 size={16} /> Resolve</button></div>
          <div className="message-stream">{messages.map((message) => <div key={message.id} className={`message ${message.sender_type}`}><span>{message.sender_type === "agent" ? "You" : "Customer"}</span><p>{message.content}</p><time>{formatTime(message.created_at)}</time></div>)}</div>
          {error && <div className="inline-error">{error}</div>}
          <form onSubmit={send} className="composer"><input aria-label="Message customer" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Write a clear, helpful response…" /><button aria-label="Send message"><Send size={18} /></button></form>
        </> : <div className="no-conversation"><div><Headphones size={34} /></div><h2>Ready for the next conversation</h2><p>Select assigned work or accept an interaction from the queue.</p></div>}
      </section>
      <aside className="assist-panel"><div className="assist-title"><div><Sparkles size={17} /></div><span>LIVE ASSIST</span><i /></div><div className="assist-card primary"><span>NEXT BEST ACTION</span><strong>{selected ? "Acknowledge the request, then confirm the order reference." : "Guidance appears when an interaction is active."}</strong><small>Campaign playbook · local rules</small></div><div className="checklist"><div className="checklist-head"><span>Required steps</span><b>0 / 3</b></div>{["Confirm customer identity", "Acknowledge the issue", "Recap the resolution"].map((step) => <label key={step}><i />{step}</label>)}</div><div className="knowledge-card"><BookOpen size={17} /><div><span>KNOWLEDGE</span><strong>Search results will follow conversation context.</strong></div></div><div className="privacy-note"><ShieldCheck size={15} /> Processing mode: <b>Local</b></div></aside>
    </div>
  </div>;
}

function CustomerWidget() {
  const [name, setName] = useState(""); const [first, setFirst] = useState(""); const [language, setLanguage] = useState("en");
  const [chat, setChat] = useState<{ id: string; session: string } | null>(null); const [messages, setMessages] = useState<ChatMessage[]>([]); const [draft, setDraft] = useState(""); const [error, setError] = useState("");
  async function start(event: FormEvent) { event.preventDefault(); try { const result = await api.startChat(name, first, language); setChat({ id: result.conversation_id, session: result.session_token }); setMessages(await api.customerMessages(result.conversation_id, result.session_token)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start chat"); } }
  async function send(event: FormEvent) { event.preventDefault(); if (!chat || !draft.trim()) return; await api.sendCustomerMessage(chat.id, chat.session, draft.trim()); setDraft(""); setMessages(await api.customerMessages(chat.id, chat.session)); }
  useEffect(() => { if (!chat) return; const timer = window.setInterval(async () => { try { setMessages(await api.customerMessages(chat.id, chat.session)); } catch { /* A transient poll failure must not break the customer session. */ } }, 2000); return () => clearInterval(timer); }, [chat]);
  return <main className="widget-page"><section className="widget-card"><header><div className="widget-logo"><Waveform size={19} /></div><div><strong>Aperture Support</strong><span><i /> Agents online</span></div></header>{!chat ? <form onSubmit={start} className="widget-start"><div><span className="section-kicker">PRIVATE SUPPORT</span><h1>How can we help?</h1><p>Start a secure conversation with our team.</p></div><label>Your name<input aria-label="Your name" required value={name} onChange={(e) => setName(e.target.value)} /></label><label>Language<select aria-label="Preferred language" value={language} onChange={(e) => setLanguage(e.target.value)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="mr">मराठी</option><option value="hi-en">Hinglish</option></select></label><label>Message<textarea aria-label="Initial message" required value={first} onChange={(e) => setFirst(e.target.value)} placeholder="Tell us what you need help with…" /></label>{error && <div className="form-error">{error}</div>}<button className="primary-button">Start conversation <ChevronRight size={18} /></button></form> : <div className="widget-chat"><div className="widget-status"><span>Connected to support</span><StatusPill status="active" /></div><div className="message-stream">{messages.map((message) => <div className={`message ${message.sender_type}`} key={message.id}><span>{message.sender_type === "customer" ? "You" : "Support"}</span><p>{message.content}</p><time>{formatTime(message.created_at)}</time></div>)}</div><form onSubmit={send} className="composer"><input aria-label="Reply" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Type your reply…" /><button aria-label="Send"><Send size={18} /></button></form></div>}<footer><ShieldCheck size={14} /> Secured by the on-prem contact centre</footer></section></main>;
}

export function App() {
  const widget = new URLSearchParams(window.location.search).has("widget");
  const [auth, setAuth] = useState<{ token: string; user: User } | null>(() => { const raw = sessionStorage.getItem("bpo-auth"); return raw ? JSON.parse(raw) : null; });
  const [page, setPage] = useState(window.platformRuntime?.desktop ? "workspace" : "overview");
  const [conversations, setConversations] = useState<Conversation[]>([]); const [queued, setQueued] = useState<Conversation[]>([]); const [agents, setAgents] = useState<AgentRow[]>([]); const [summary, setSummary] = useState<{ conversations: Record<string, number>; agents: Record<string, number> } | null>(null);
  const isAgent = auth?.user.role === "agent";
  const refresh = useCallback(async () => { if (!auth) return; const own = await api.conversations(auth.token); setConversations(own); if (auth.user.role === "agent") setQueued(await api.queued(auth.token)); else { if (auth.user.role !== "client_viewer") setAgents(await api.agents(auth.token)); setSummary(await api.summary(auth.token)); } }, [auth]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!auth) return; const ws = connectRealtime(auth.token, () => void refresh()); return () => ws.close(); }, [auth, refresh]);
  const login = (token: string, user: User) => { const next = { token, user }; sessionStorage.setItem("bpo-auth", JSON.stringify(next)); setAuth(next); setPage(user.role === "agent" ? "workspace" : "overview"); };
  const logout = () => { sessionStorage.removeItem("bpo-auth"); setAuth(null); };
  if (widget) return <CustomerWidget />;
  if (!auth) return <Login onLogin={login} />;
  return <div className="app-frame"><Sidebar user={auth.user} page={page} onPage={setPage} onLogout={logout} /><main className="main-canvas">{isAgent ? <AgentView token={auth.token} user={auth.user} assigned={conversations} queued={queued} onRefresh={() => void refresh()} /> : <SupervisorView token={auth.token} user={auth.user} conversations={conversations} agents={agents} summary={summary} refresh={() => void refresh()} />}</main></div>;
}
