import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, AudioWaveform as Waveform, BarChart3, BookOpen, CheckCircle2, ChevronRight,
  ClipboardCheck, Clock3, Headphones, Inbox, LayoutDashboard, LockKeyhole,
  Download, FileText, LogOut, MessageSquareText, MicOff, Pause, Phone, PhoneCall,
  PhoneOff, Play, Send, Settings, ShieldCheck, Sparkles, UsersRound,
} from "lucide-react";
import { api, ApiError, connectRealtime } from "./api";
import type { AgentRow, AssistEvent, ChatMessage, Conversation, EvidenceProvenance, QAEvaluation, TranscriptSegment, User, VoiceSession } from "./types";
import { CallCapture } from "./callCapture";
import { SipPhone, type SipStatus } from "./sip";

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
      <div className="story-signal"><div className="pulse-ring"><Waveform size={28} /></div><div><strong>Platform online</strong><span>Private local deployment</span></div></div>
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
    ? [["workspace", Headphones, "Workspace"]]
    : [["overview", LayoutDashboard, "Overview"], ["conversations", MessageSquareText, "Conversations"], ["intelligence", Sparkles, "Intelligence"], ["quality", ClipboardCheck, "Quality"], ["coaching", UsersRound, "Coaching"], ["team", UsersRound, "Live floor"], ["reports", BarChart3, "Reports"]];
  return <aside className="sidebar">
    <div className="sidebar-brand"><div><Waveform size={20} /></div><span>APERTURE <b>CX</b></span></div>
    <nav>{items.map(([id, Icon, label]) => <button key={id as string} onClick={() => onPage(id as string)} className={page === id ? "active" : ""}><Icon size={18} /><span>{label as string}</span></button>)}</nav>
    <div className="sidebar-bottom">
      {user.role === "admin" && <button onClick={() => onPage("settings")}><Settings size={18} /><span>Settings</span></button>}
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
    <header className="page-header"><div><span className="section-kicker">OPERATIONS COMMAND</span><h1>Welcome, {user.display_name.split(" ")[0]}</h1><p>Measured activity across the current evidence dataset and live queue.</p></div><div className="header-actions"><span className="live-button"><i /> Connected</span></div></header>
    <section className="metric-grid">
      <article><div className="metric-icon emerald"><Phone size={20} /></div><div><span>Active interactions</span><strong>{active}</strong><small><b>Live</b> across voice + chat</small></div></article>
      <article><div className="metric-icon amber"><Clock3 size={20} /></div><div><span>Waiting in queue</span><strong>{queued}</strong><small>Oldest shown first</small></div></article>
      <article><div className="metric-icon blue"><UsersRound size={20} /></div><div><span>Agents available</span><strong>{available}<em> / {agents.length}</em></strong><small>Current floor state</small></div></article>
      <article><div className="metric-icon violet"><CheckCircle2 size={20} /></div><div><span>Resolved</span><strong>{closed}</strong><small>Current pilot dataset</small></div></article>
    </section>
    <section className="dashboard-grid">
      <article className="panel interaction-panel">
        <div className="panel-head"><div><h3>Recent interactions</h3><p>Voice and digital records in one evidence trail</p></div><button onClick={refresh}>Refresh</button></div>
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

function ConversationExplorer({ token, conversations }: { token: string; conversations: Conversation[] }) {
  const [selected, setSelected] = useState(conversations[0]?.id || "");
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [assist, setAssist] = useState<AssistEvent[]>([]);
  const [evidence, setEvidence] = useState<EvidenceProvenance | null>(null);
  const current = conversations.find((item) => item.id === selected);
  useEffect(() => { if (!current) return; void (async () => { const [nextAssist, nextEvidence] = await Promise.all([api.assist(token, current.id), api.evidence(token, current.id)]); setAssist(nextAssist); setEvidence(nextEvidence); if (current.channel === "voice") { setTranscript(await api.transcript(token, current.id)); setMessages([]); } else { setMessages(await api.messages(token, current.id)); setTranscript([]); } })(); }, [current, token]);
  return <div className="page-content"><header className="page-header"><div><span className="section-kicker">UNIFIED HISTORY</span><h1>Conversations</h1><p>One evidence trail across voice and digital channels.</p></div></header><section className="explorer-grid"><article className="panel conversation-index">{conversations.map((item) => <button className={selected === item.id ? "selected" : ""} onClick={() => setSelected(item.id)} key={item.id}><div className={`channel-badge ${item.channel}`}>{item.channel === "voice" ? <Phone size={16} /> : <MessageSquareText size={16} />}</div><span><strong>{item.channel.replace("_", " ")}</strong><small>{item.language.toUpperCase()} · {formatTime(item.started_at)}</small></span><StatusPill status={item.status} /></button>)}</article><article className="panel evidence-view">{current ? <><div className="panel-head"><div><h3>{current.channel === "voice" ? "Voice evidence" : "Digital timeline"}</h3><p>{current.summary || "Interaction evidence and assist history"}</p></div><ShieldCheck size={18} /></div>{evidence && <div className="provenance-card"><div><ShieldCheck size={16} /><strong>{evidence.label}</strong><span>{evidence.license || evidence.classification.replaceAll("_", " ")}</span></div><p>{evidence.boundary}</p>{evidence.source_url && <a href={evidence.source_url} target="_blank" rel="noreferrer">{evidence.source_name} · {evidence.source_id}</a>}</div>}<div className="evidence-body">{transcript.map((segment) => <div className="evidence-line" key={segment.id}><span>{segment.speaker}</span><p>{segment.text}</p><time>{Math.floor(segment.start_ms / 1000)}s</time></div>)}{messages.map((message) => <div className="evidence-line" key={message.id}><span>{message.sender_type}</span><p>{message.content}</p><time>{formatTime(message.created_at)}</time></div>)}{assist.map((event) => <div className="assist-evidence" key={event.id}><Sparkles size={15} /><div><b>{event.title}</b><span>{event.content}</span></div></div>)}</div></> : <div className="empty-state">No conversation selected.</div>}</article></section></div>;
}

function QualityView({ token, canReview }: { token: string; canReview: boolean }) {
  const [evaluations, setEvaluations] = useState<QAEvaluation[]>([]); const [selected, setSelected] = useState(""); const [detail, setDetail] = useState<Record<string, unknown> | null>(null); const [score, setScore] = useState(90); const [reason, setReason] = useState("Reviewed against the recording and evidence spans.");
  const load = useCallback(async () => { const rows = await api.qaEvaluations(token); setEvaluations(rows); setSelected((value) => value || rows[0]?.id || ""); }, [token]);
  useEffect(() => { void load(); }, [load]); useEffect(() => { if (selected) void api.qaDetail(token, selected).then(setDetail); }, [selected, token]);
  async function review(event: FormEvent) { event.preventDefault(); await api.reviewQA(token, selected, score, reason); await load(); setDetail(await api.qaDetail(token, selected)); }
  const answers = (detail?.answers as Array<Record<string, unknown>> | undefined) || [];
  return <div className="page-content"><header className="page-header"><div><span className="section-kicker">EVIDENCE-LED QUALITY</span><h1>Quality review</h1><p>Automatic scoring stays immutable when a human reviewer overrides it.</p></div></header><section className="quality-grid"><article className="panel score-list">{evaluations.map((item) => <button className={selected === item.id ? "selected" : ""} onClick={() => setSelected(item.id)} key={item.id}><div className="score-ring">{item.effective_score}</div><span><strong>{item.status === "reviewed" ? "Human reviewed" : "Automatic evaluation"}</strong><small>{item.provider} · {formatTime(item.created_at)}</small></span><ChevronRight size={17} /></button>)}</article><article className="panel qa-detail"><div className="panel-head"><div><h3>Evaluation evidence</h3><p>Original automatic score: {String(detail?.automatic_score ?? "—")}</p></div><ClipboardCheck size={18} /></div><div className="qa-answers">{answers.map((answer) => <div key={String(answer.id)}><span className={answer.passed ? "pass" : "fail"}>{answer.passed ? "PASS" : "FAIL"}</span><strong>{String(answer.question)}</strong><p>“{String(answer.evidence_quote)}”</p><small>{String(answer.evidence_start_ms)}–{String(answer.evidence_end_ms)} ms · confidence {String(answer.confidence)}%</small></div>)}</div>{canReview && selected && <form className="review-form" onSubmit={review}><label>Reviewed score<input aria-label="Reviewed score" type="number" min="0" max="100" value={score} onChange={(event) => setScore(Number(event.target.value))} /></label><label>Reason<input aria-label="Review reason" value={reason} onChange={(event) => setReason(event.target.value)} /></label><button>Save review</button></form>}</article></section></div>;
}

function IntelligenceView({ token }: { token: string }) {
  const [query, setQuery] = useState(""); const [results, setResults] = useState<Array<Record<string, unknown>>>([]); const [loading, setLoading] = useState(false);
  async function search(event: FormEvent) { event.preventDefault(); if (query.trim().length < 2) return; setLoading(true); try { setResults(await api.searchIntelligence(token, query)); } finally { setLoading(false); } }
  return <div className="page-content"><header className="page-header"><div><span className="section-kicker">CONVERSATION INTELLIGENCE</span><h1>Find the signal behind every interaction</h1><p>Search the indexed transcript corpus by customer wording, topic, resolution or compliance phrase.</p></div></header><form className="intelligence-search" onSubmit={search}><input aria-label="Search conversations" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try: card, password, branch, payment…" /><button className="live-button">{loading ? "Searching…" : "Search evidence"}</button></form><section className="panel search-results"><div className="panel-head"><div><h3>Evidence matches</h3><p>{results.length ? `${results.length} matching transcript moments` : "Search requires at least two characters."}</p></div><Sparkles size={18} /></div>{results.map((item, index) => <div className="search-result" key={`${item.conversation_id}-${index}`}><span>{String(item.disposition || "Unclassified")}</span><strong>{String(item.speaker).toUpperCase()}</strong><p>{String(item.text)}</p><small>{String(item.channel)} · {Math.floor(Number(item.start_ms || 0) / 1000)}s</small></div>)}</section></div>;
}

function CoachingView({ token, user }: { token: string; user: User }) {
  const [actions, setActions] = useState<Array<Record<string, unknown>>>([]); const [evaluations, setEvaluations] = useState<QAEvaluation[]>([]); const [evaluationId, setEvaluationId] = useState(""); const [focus, setFocus] = useState("Improve the failed rubric checks using evidence-linked examples."); const [plan, setPlan] = useState("Review the recording, rehearse the improved response, and bring one example to the next calibration.");
  const load = useCallback(async () => { const [nextActions, nextEvaluations] = await Promise.all([api.coachingActions(token), api.qaEvaluations(token)]); setActions(nextActions); setEvaluations(nextEvaluations); setEvaluationId((value) => value || nextEvaluations[0]?.id || ""); }, [token]); useEffect(() => { void load(); }, [load]);
  async function create(event: FormEvent) { event.preventDefault(); await api.createCoachingAction(token, { evaluation_id: evaluationId, focus, action_plan: plan }); await load(); }
  async function acknowledge(id: string) { await api.acknowledgeCoachingAction(token, id); await load(); }
  return <div className="page-content"><header className="page-header"><div><span className="section-kicker">COACHING LOOP</span><h1>Turn QA evidence into improvement</h1><p>Assign a specific improvement action from an evaluation and track acknowledgement.</p></div></header>{user.role !== "agent" && <form className="panel coaching-form" onSubmit={create}><div className="panel-head"><div><h3>Create coaching action</h3><p>Connected to the immutable QA evaluation.</p></div><ClipboardCheck size={18} /></div><label>Evaluation<select aria-label="Coaching evaluation" value={evaluationId} onChange={(event) => setEvaluationId(event.target.value)}>{evaluations.map((item) => <option key={item.id} value={item.id}>QA {item.effective_score} · {item.summary.slice(0, 48)}</option>)}</select></label><label>Focus<input aria-label="Coaching focus" value={focus} onChange={(event) => setFocus(event.target.value)} /></label><label>Action plan<textarea aria-label="Coaching action plan" value={plan} onChange={(event) => setPlan(event.target.value)} /></label><button>Create action</button></form>}<section className="panel coaching-list"><div className="panel-head"><div><h3>Coaching actions</h3><p>Open and acknowledged actions by agent.</p></div><UsersRound size={18} /></div>{actions.map((item) => <div className="coaching-row" key={String(item.id)}><div><strong>{String(item.agent)}</strong><span>{String(item.status)}</span></div><p><b>{String(item.focus)}</b>{String(item.action_plan)}</p>{user.role === "agent" && item.status === "open" && <button onClick={() => void acknowledge(String(item.id))}>Acknowledge</button>}</div>)}</section></div>;
}

function ReportsView({ token, user }: { token: string; user: User }) {
  const [summary, setSummary] = useState<Record<string, unknown>>({}); const [costs, setCosts] = useState<{ items?: Array<Record<string, unknown>>; total_cost_micros_inr?: number }>({}); const [config, setConfig] = useState<Record<string, unknown>>({}); const [agents, setAgents] = useState<AgentRow[]>([]); const [channel, setChannel] = useState(""); const [campaign, setCampaign] = useState(""); const [queue, setQueue] = useState(""); const [agent, setAgent] = useState("");
  const query = useMemo(() => { const params = new URLSearchParams(); if (channel) params.set("channel", channel); if (campaign) params.set("campaign_id", campaign); if (queue) params.set("queue_id", queue); if (agent) params.set("agent_id", agent); return params.size ? `?${params}` : ""; }, [channel, campaign, queue, agent]);
  useEffect(() => { void Promise.all([api.configuration(token), user.role === "client_viewer" ? Promise.resolve([]) : api.agents(token), api.reportCosts(token)]).then(([nextConfig, nextAgents, nextCosts]) => { setConfig(nextConfig); setAgents(nextAgents as AgentRow[]); setCosts(nextCosts as typeof costs); }); }, [token, user.role]);
  useEffect(() => { void api.reportSummary(token, query).then(setSummary); }, [token, query]);
  async function download(format: "csv" | "pdf") { const blob = await api.downloadReport(token, format, query); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `aperture-cx-report.${format}`; anchor.click(); URL.revokeObjectURL(url); }
  const campaigns = (config.campaigns || []) as Array<Record<string, unknown>>; const queues = (config.queues || []) as Array<Record<string, unknown>>;
  const mix = (summary.mix || {}) as Record<string, Array<Record<string, unknown>>>; const quality = (summary.quality || {}) as Record<string, Array<Record<string, unknown>>>;
  const trend = (summary.trend || []) as Array<Record<string, unknown>>; const reportAgents = (summary.agents || []) as Array<Record<string, unknown>>;
  const BarList = ({ rows, valueKey = "count" }: { rows: Array<Record<string, unknown>>; valueKey?: string }) => { const maximum = Math.max(1, ...rows.map((item) => Number(item[valueKey] || 0))); return <div className="bar-list">{rows.map((item) => { const value = Number(item[valueKey] || 0); return <div key={String(item.label || item.date || item.agent)}><span>{String(item.label || item.date || item.agent)}</span><i><b style={{ width: `${value / maximum * 100}%` }} /></i><strong>{value}</strong></div>; })}</div>; };
  return <div className="page-content"><header className="page-header"><div><span className="section-kicker">CLIENT-READY INTELLIGENCE</span><h1>Reports & economics</h1><p>Collected outcomes, predictions, and usage-based cost estimates remain visibly separate.</p></div><div className="header-actions"><button className="ghost-button" onClick={() => void download("csv")}><Download size={16} /> CSV</button><button className="live-button" onClick={() => void download("pdf")}><FileText size={16} /> PDF</button></div></header><section className="report-filters"><label>Channel<select aria-label="Report channel" value={channel} onChange={(event) => setChannel(event.target.value)}><option value="">All channels</option><option value="voice">Voice</option><option value="web_chat">Web chat</option></select></label><label>Campaign<select aria-label="Report campaign" value={campaign} onChange={(event) => setCampaign(event.target.value)}><option value="">All campaigns</option>{campaigns.map((item) => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}</select></label><label>Queue / team<select aria-label="Report queue" value={queue} onChange={(event) => setQueue(event.target.value)}><option value="">All queues</option>{queues.map((item) => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}</select></label>{user.role !== "client_viewer" && <label>Agent<select aria-label="Report agent" value={agent} onChange={(event) => setAgent(event.target.value)}><option value="">All agents</option>{agents.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>}</section><section className="metric-grid report-metrics"><article><div className="metric-icon emerald"><MessageSquareText size={20} /></div><div><span>Conversations</span><strong>{String(summary.conversation_count ?? 0)}</strong><small>Current authorized scope</small></div></article><article><div className="metric-icon violet"><ClipboardCheck size={20} /></div><div><span>Average QA</span><strong>{String(summary.average_qa ?? "—")}</strong><small>Reviewed value wins</small></div></article><article><div className="metric-icon blue"><Activity size={20} /></div><div><span>Predicted risk</span><strong>{String(summary.average_predicted_risk ?? "—")}</strong><small>Prediction, not survey CSAT</small></div></article><article><div className="metric-icon amber"><BarChart3 size={20} /></div><div><span>Recorded CSAT</span><strong>{String(summary.average_actual_csat ?? "—")}</strong><small>{String(summary.actual_csat_count ?? 0)} collected responses</small></div></article></section><section className="report-grid"><article className="panel"><div className="panel-head"><div><h3>Interaction mix</h3><p>Channel, language and case intent</p></div><BarChart3 size={18} /></div><div className="report-columns"><div><h4>By disposition</h4><BarList rows={mix.dispositions || []} /></div><div><h4>By channel</h4><BarList rows={mix.channels || []} /></div><div><h4>By language</h4><BarList rows={mix.languages || []} /></div></div></article><article className="panel"><div className="panel-head"><div><h3>Quality & risk</h3><p>Traceable rubric results and predictive satisfaction signal</p></div><ClipboardCheck size={18} /></div><div className="report-columns"><div><h4>QA score distribution</h4><BarList rows={quality.score_distribution || []} /></div><div><h4>Risk distribution</h4><BarList rows={quality.risk_distribution || []} /></div><div><h4>Top failed checks</h4><BarList rows={quality.failed_checks || []} valueKey="failed" /></div></div></article><article className="panel"><div className="panel-head"><div><h3>Source interaction trend</h3><p>Historical source dates shown as-is; not a live-volume claim.</p></div><Activity size={18} /></div><div className="trend-list"><BarList rows={trend} valueKey="interactions" /></div></article><article className="panel"><div className="panel-head"><div><h3>Agent comparison</h3><p>Volume with quality and predicted-risk context</p></div><UsersRound size={18} /></div><div className="table-wrap"><table><thead><tr><th>Agent</th><th>Interactions</th><th>Avg QA</th><th>Avg risk</th><th>Fatal</th></tr></thead><tbody>{reportAgents.map((item) => <tr key={String(item.agent_id)}><td>{String(item.agent)}</td><td>{String(item.interactions)}</td><td>{String(item.average_qa ?? "—")}</td><td>{String(item.average_risk ?? "—")}</td><td>{String(item.fatal_flags)}</td></tr>)}</tbody></table></div></article></section><article className="panel cost-table"><div className="panel-head"><div><h3>Usage-based cost estimate</h3><p>Measured provider units multiplied by configured rates; this is not an invoice.</p></div><strong>₹{((costs.total_cost_micros_inr || 0) / 1_000_000).toFixed(2)}</strong></div><div className="cost-rows">{(costs.items || []).map((item) => <div key={`${item.category}-${item.provider}`}><span>{String(item.category)}</span><b>{String(item.provider)}</b><em>{String(item.units)} {String(item.unit_name)}</em><strong>₹{(Number(item.cost_micros_inr) / 1_000_000).toFixed(2)}</strong></div>)}</div></article></div>;
}

function ConfigurationView({ token, admin }: { token: string; admin: boolean }) {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null); const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(null); const [saved, setSaved] = useState("");
  const [campaignName, setCampaignName] = useState(""); const [queueName, setQueueName] = useState(""); const [scriptContent, setScriptContent] = useState(""); const [knowledgeTitle, setKnowledgeTitle] = useState(""); const [knowledgeContent, setKnowledgeContent] = useState(""); const [qaName, setQaName] = useState("");
  const [userEmail, setUserEmail] = useState(""); const [userName, setUserName] = useState(""); const [userRole, setUserRole] = useState("agent"); const [userPassword, setUserPassword] = useState("PilotUser123!");
  const load = useCallback(async () => { const next = await api.configuration(token); setConfig(next); const campaigns = (next.campaigns || []) as Array<Record<string, unknown>>; const queues = (next.queues || []) as Array<Record<string, unknown>>; const scripts = (next.scripts || []) as Array<Record<string, unknown>>; const knowledge = (next.knowledge || []) as Array<Record<string, unknown>>; const forms = (next.qa_forms || []) as Array<Record<string, unknown>>; setCampaignName(String(campaigns[0]?.name || "")); setQueueName(String(queues[0]?.name || "")); setScriptContent(String(scripts[0]?.content || "")); setKnowledgeTitle(String(knowledge[0]?.title || "")); setKnowledgeContent(String(knowledge[0]?.content || "")); setQaName(String(forms[0]?.name || "")); if (admin) setDiagnostics(await api.diagnostics(token)); }, [token, admin]); useEffect(() => { void load(); }, [load]);
  const tenant = (config?.tenant || {}) as Record<string, unknown>; const scripts = (config?.scripts || []) as Array<Record<string, unknown>>; const knowledge = (config?.knowledge || []) as Array<Record<string, unknown>>; const users = (config?.users || []) as Array<Record<string, unknown>>; const privacy = (diagnostics?.privacy || {}) as Record<string, unknown>;
  async function toggleMode() { await api.updatePrivacy(token, tenant.ai_mode === "local" ? "external" : "local"); await load(); }
  async function savePilot(event: FormEvent) { event.preventDefault(); await api.updatePilot(token, { campaign_name: campaignName, queue_name: queueName, script_content: scriptContent, required_steps: ["Professional greeting", "Understand the caller task", "Give the source-backed answer", "Offer further help", "Close professionally"], knowledge_title: knowledgeTitle, knowledge_content: knowledgeContent, qa_form_name: qaName }); setSaved("Pilot configuration saved and audited."); await load(); }
  async function addUser(event: FormEvent) { event.preventDefault(); await api.createUser(token, { email: userEmail, display_name: userName, role: userRole, password: userPassword }); setUserEmail(""); setUserName(""); setSaved(userRole === "agent" ? "User created and assigned to the pilot queue." : userRole === "client_viewer" ? "Client viewer created with pilot campaign access." : "User created with the selected role."); await load(); }
  return <div className="page-content"><header className="page-header"><div><span className="section-kicker">DEPLOYMENT CONTROL</span><h1>Platform configuration</h1><p>Campaign playbooks and privacy mode shared by every channel.</p></div>{admin && <button className="live-button" onClick={() => void toggleMode()}><ShieldCheck size={16} /> {String(tenant.ai_mode || "external")} mode</button>}</header><section className="config-grid"><article className="panel"><div className="panel-head"><div><h3>Privacy boundary</h3><p>Current content-processing path</p></div><StatusPill status={String(tenant.ai_mode || "external")} /></div><div className="config-copy"><strong>{tenant.ai_mode === "local" ? "Customer content stays inside the deployment." : "External AI mode is enabled."}</strong><p>Provider: {String(privacy.provider || "external_config_required")}. Customer-content egress: {String(privacy.customer_content_egress ?? true)}.</p></div></article><article className="panel"><div className="panel-head"><div><h3>Active script</h3><p>{String(scripts[0]?.name || "Not configured")}</p></div><FileText size={18} /></div><div className="config-copy"><p>{String(scripts[0]?.content || "")}</p></div></article><article className="panel"><div className="panel-head"><div><h3>Knowledge base</h3><p>{knowledge.length} active articles</p></div><BookOpen size={18} /></div><div className="config-copy"><strong>{String(knowledge[0]?.title || "No articles")}</strong><p>{String(knowledge[0]?.content || "")}</p></div></article></section>{admin && <section className="admin-config-grid"><form className="panel admin-form" onSubmit={savePilot}><div className="panel-head"><div><h3>Pilot operating model</h3><p>Campaign, queue, script, knowledge, and QA form</p></div><Settings size={18} /></div><div className="form-grid"><label>Campaign<input aria-label="Campaign name" value={campaignName} onChange={(event) => setCampaignName(event.target.value)} /></label><label>Queue<input aria-label="Queue name" value={queueName} onChange={(event) => setQueueName(event.target.value)} /></label><label>QA form<input aria-label="QA form name" value={qaName} onChange={(event) => setQaName(event.target.value)} /></label><label className="wide">Agent script<textarea aria-label="Agent script" value={scriptContent} onChange={(event) => setScriptContent(event.target.value)} /></label><label>Knowledge title<input aria-label="Knowledge title" value={knowledgeTitle} onChange={(event) => setKnowledgeTitle(event.target.value)} /></label><label className="wide">Knowledge content<textarea aria-label="Knowledge content" value={knowledgeContent} onChange={(event) => setKnowledgeContent(event.target.value)} /></label><button>Save operating model</button></div></form><form className="panel admin-form" onSubmit={addUser}><div className="panel-head"><div><h3>Users & access</h3><p>{users.length} provisioned identities</p></div><UsersRound size={18} /></div><div className="form-grid single"><label>Name<input aria-label="New user name" required value={userName} onChange={(event) => setUserName(event.target.value)} /></label><label>Email<input aria-label="New user email" required type="email" value={userEmail} onChange={(event) => setUserEmail(event.target.value)} /></label><label>Role<select aria-label="New user role" value={userRole} onChange={(event) => setUserRole(event.target.value)}><option value="agent">Agent</option><option value="supervisor">Supervisor</option><option value="qa_reviewer">QA reviewer</option><option value="client_viewer">Client viewer</option></select></label><label>Temporary password<input aria-label="New user password" value={userPassword} onChange={(event) => setUserPassword(event.target.value)} /></label><button>Create user</button></div></form></section>}{saved && <div className="save-toast"><CheckCircle2 size={16} />{saved}</div>}</div>;
}

function AgentView({ token, user, assigned, queued, onRefresh }: { token: string; user: User; assigned: Conversation[]; queued: Conversation[]; onRefresh: () => void }) {
  const activeWork = assigned.filter((item) => item.status === "active" || item.status === "wrap_up");
  const [selectedId, setSelectedId] = useState<string | null>(activeWork[0]?.id || null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [assist, setAssist] = useState<AssistEvent[]>([]);
  const [voice, setVoice] = useState<VoiceSession | null>(null);
  const [recordingUrl, setRecordingUrl] = useState("");
  const recordingRef = useRef<{ id: string; url: string } | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [draft, setDraft] = useState("");
  const [phone, setPhone] = useState(window.platformRuntime?.sip?.enabled ? "2003" : "+919999999999");
  const [callLanguage, setCallLanguage] = useState("en");
  const [presence, setPresence] = useState("available");
  const [error, setError] = useState("");
  const [sipStatus, setSipStatus] = useState<SipStatus>("disabled");
  const [sipDetail, setSipDetail] = useState("Demo media mode");
  const sipRef = useRef<SipPhone | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const captureRef = useRef<CallCapture | null>(null);
  const selectedIdRef = useRef<string | null>(selectedId);
  const voiceRef = useRef<VoiceSession | null>(voice);
  const pendingInboundIdRef = useRef<string | null>(null);
  const incomingSipAliveRef = useRef(false);
  const endingRef = useRef(false);
  const selected = assigned.find((item) => item.id === selectedId);
  selectedIdRef.current = selectedId;
  voiceRef.current = voice;

  const loadConversation = useCallback(async () => {
    if (!selectedId || !selected) { setMessages([]); setTranscript([]); setAssist([]); setVoice(null); return; }
    setError("");
    try {
      setAssist(await api.assist(token, selectedId));
      if (selected.channel === "web_chat") {
        setMessages(await api.messages(token, selectedId)); setTranscript([]); setVoice(null);
      } else {
        const call = await api.voiceCall(token, selectedId); setVoice(call.session); setTranscript(await api.transcript(token, selectedId));
        if (call.session.state === "ended" && call.session.recording_available && recordingRef.current?.id !== selectedId) {
          const staleRecordingUrl = recordingRef.current?.url;
          if (staleRecordingUrl) { setRecordingUrl(""); window.setTimeout(() => URL.revokeObjectURL(staleRecordingUrl), 500); }
          recordingRef.current = { id: selectedId, url: "" };
          try { const blob = await api.recording(token, selectedId); const url = URL.createObjectURL(blob); recordingRef.current = { id: selectedId, url }; setRecordingUrl(url); } catch (reason) { recordingRef.current = null; throw reason; }
        }
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load conversation"); }
  }, [selectedId, selected, token]);
  const loadConversationRef = useRef(loadConversation);
  loadConversationRef.current = loadConversation;
  useEffect(() => { void loadConversation(); }, [loadConversation]);
  useEffect(() => () => { if (recordingRef.current?.url) URL.revokeObjectURL(recordingRef.current.url); }, []);
  useEffect(() => {
    const phoneClient = new SipPhone({
      onStatus: (status, detail) => { setSipStatus(status); setSipDetail(detail || status); },
      onIncoming: (remote) => {
        incomingSipAliveRef.current = true;
        void (async () => {
          try {
            const result = await api.registerLiveInbound(token, remote, `Live SIP caller ${remote}`, "auto");
            if (!incomingSipAliveRef.current) { await api.rejectVoice(token, result.conversation.id); onRefresh(); return; }
            pendingInboundIdRef.current = result.conversation.id;
            onRefresh();
          } catch (reason) {
            phoneClient.reject();
            setError(reason instanceof Error ? reason.message : "Incoming SIP call could not be registered");
          }
        })();
      },
      onEnded: () => {
        incomingSipAliveRef.current = false;
        if (endingRef.current) { endingRef.current = false; return; }
        const pendingId = pendingInboundIdRef.current;
        if (pendingId) {
          pendingInboundIdRef.current = null;
          void api.rejectVoice(token, pendingId).then(onRefresh).catch(() => onRefresh());
          return;
        }
        const id = selectedIdRef.current;
        if (!id || !voiceRef.current || voiceRef.current.state === "ended") return;
        void (async () => {
          try {
            await stopCaptureAndUpload(id);
            const next = await api.voiceControl(token, id, "hangup");
            setVoice(next); await loadConversationRef.current(); onRefresh();
          } catch (reason) { setError(reason instanceof Error ? reason.message : "Remote hang-up could not be finalized"); }
        })();
      },
      onMedia: (remote, local) => {
        if (remoteAudioRef.current) { remoteAudioRef.current.srcObject = remote; void remoteAudioRef.current.play().catch(() => undefined); }
        if (voiceRef.current?.provider === "groq_external" && !captureRef.current) {
          captureRef.current = new CallCapture(remote, local, async (blob, startMs, speaker) => {
            const id = selectedIdRef.current;
            if (!id) return;
            try {
              const result = await api.ingestVoiceChunk(token, id, blob, startMs, speaker);
              if (result.guidance_error) setError(`Live guidance provider error: ${result.guidance_error}`);
              await loadConversationRef.current();
            } catch (reason) {
              setError(reason instanceof Error ? `Live AI chunk failed: ${reason.message}` : "Live AI chunk failed");
            }
          });
        }
      },
    });
    sipRef.current = phoneClient;
    phoneClient.start();
    return () => { phoneClient.stop(); sipRef.current = null; };
  // SIP is a workstation-lifetime service; changing interaction state is read through refs.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function claim(id: string) {
    setError("");
    try {
      await api.claim(token, id);
      setSelectedId(id); selectedIdRef.current = id;
      if (pendingInboundIdRef.current === id) {
        const call = await api.voiceCall(token, id);
        setVoice(call.session); voiceRef.current = call.session;
        pendingInboundIdRef.current = null;
        incomingSipAliveRef.current = true;
        sipRef.current?.answer();
      }
      onRefresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Interaction could not be accepted"); }
  }
  async function reject(id: string) {
    setError("");
    try {
      if (pendingInboundIdRef.current === id) { pendingInboundIdRef.current = null; incomingSipAliveRef.current = false; sipRef.current?.reject(); }
      await api.rejectVoice(token, id); onRefresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Interaction could not be rejected"); }
  }
  async function send(event: FormEvent) { event.preventDefault(); if (!selectedId || !draft.trim()) return; await api.sendMessage(token, selectedId, draft.trim()); setDraft(""); await loadConversation(); }
  async function changePresence(value: string) { setPresence(value); await api.presence(token, value); }
  async function resolve() { if (!selectedId) return; await api.wrapUp(token, selectedId, "resolved", selected?.summary || "Customer request resolved during the interaction."); setSelectedId(null); onRefresh(); }
  async function stopCaptureAndUpload(id: string) {
    const capture = captureRef.current;
    captureRef.current = null;
    if (!capture) return;
    const result = await capture.stop();
    if (result.blob.size) await api.uploadRecording(token, id, result.blob, result.durationMs);
  }
  async function dial(event: FormEvent) { event.preventDefault(); setError(""); try {
    const sipEnabled = Boolean(window.platformRuntime?.sip?.enabled);
    if (sipEnabled && sipStatus !== "registered") throw new Error(`SIP phone is not ready: ${sipDetail}`);
    const result = await api.dialVoice(token, phone, sipEnabled ? "Live SIP customer" : "AI sample customer", callLanguage);
    setSelectedId(result.conversation.id); selectedIdRef.current = result.conversation.id; setVoice(result.session); voiceRef.current = result.session;
    if (sipEnabled) sipRef.current?.call(phone);
    onRefresh();
  } catch (reason) { setError(reason instanceof Error ? reason.message : "Call could not start"); } }
  async function control(action: string, target?: string) { if (!selectedId) return;
    if (action === "mute" || action === "unmute") sipRef.current?.mute(action === "mute");
    if (action === "hold" || action === "resume") sipRef.current?.hold(action === "hold");
    if (action === "transfer" && target) sipRef.current?.transfer(target);
    if (action === "hangup") { endingRef.current = Boolean(window.platformRuntime?.sip?.enabled); await stopCaptureAndUpload(selectedId); sipRef.current?.hangup(); }
    const next = await api.voiceControl(token, selectedId, action, target); setVoice(next); voiceRef.current = next; await loadConversation(); onRefresh();
  }
  const currentAssist = assist.find((item) => item.event_type === "next_best_action") || assist[0];
  const currentKnowledge = assist.find((item) => item.event_type === "knowledge");

  return <div className="agent-shell">
    <header className="agent-topbar"><div><span className="section-kicker">AGENT WORKSPACE</span><h1>{user.display_name}</h1></div><div className="agent-statuses"><span className={`sip-indicator ${sipStatus}`}><Phone size={14} /> {sipDetail}</span><label className="presence-control"><i className={presence} /><select aria-label="Agent status" value={presence} onChange={(e) => void changePresence(e.target.value)}><option value="available">Available</option><option value="break">On break</option><option value="offline">Offline</option></select></label></div></header>
    <div className="agent-columns">
      <section className="work-list"><div className="work-list-head"><div><h3>My work</h3><span>{activeWork.length} active</span></div><button aria-label="Refresh work" onClick={onRefresh}><Activity size={16} /></button></div>
        {activeWork.map((item) => <button key={item.id} onClick={() => setSelectedId(item.id)} className={`work-item ${selectedId === item.id ? "selected" : ""}`}><div className={`channel-badge ${item.channel}`}>{item.channel === "voice" ? <Phone size={16} /> : <MessageSquareText size={16} />}</div><div><strong>{item.channel === "web_chat" ? "Digital customer" : "Voice customer"}</strong><span>{item.language.toUpperCase()} · {formatTime(item.started_at)}</span></div><StatusPill status={item.status} /></button>)}
        <div className="queue-divider"><span>AVAILABLE QUEUE</span><b>{queued.length}</b></div>
        {queued.map((item) => <div key={item.id} className="queue-item" data-conversation-id={item.id}><div>{item.channel === "voice" ? <Phone size={16} /> : <MessageSquareText size={16} />}<span><strong>{item.channel === "voice" ? "Inbound voice call" : "New web chat"}</strong><small>{item.language.toUpperCase()} · waiting</small></span></div><div className="queue-actions">{item.channel === "voice" && <button className="reject" onClick={() => void reject(item.id)}>Reject</button>}<button onClick={() => void claim(item.id)}>Accept</button></div></div>)}
        {!activeWork.length && !queued.length && <div className="empty-state"><Inbox size={28} /><strong>You're caught up</strong><span>New work will appear here.</span></div>}
      </section>
      <section className="conversation-panel">
        {selected ? <><div className="conversation-head"><div><div className={`channel-badge ${selected.channel}`}>{selected.channel === "voice" ? <Phone size={17} /> : <MessageSquareText size={17} />}</div><div><strong>{selected.channel === "voice" ? "Voice interaction" : "Customer conversation"}</strong><span>{selected.language.toUpperCase()} · {selected.channel === "voice" ? voice?.provider.replaceAll("_", " ") : "Secure session"}</span></div></div>{selected.channel === "web_chat" || voice?.state === "ended" ? <button className="resolve-button" onClick={() => void resolve()}><CheckCircle2 size={16} /> Complete wrap-up</button> : <StatusPill status={voice?.state || selected.status} />}</div>
          {selected.channel === "web_chat" ? <><div className="message-stream">{messages.map((message) => <div key={message.id} className={`message ${message.sender_type}`}><span>{message.sender_type === "agent" ? "You" : "Customer"}</span><p>{message.content}</p><time>{formatTime(message.created_at)}</time></div>)}</div><form onSubmit={send} className="composer"><input aria-label="Message customer" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Write a clear, helpful response…" /><button aria-label="Send message"><Send size={18} /></button></form></> : <div className="voice-stage">
            <audio ref={remoteAudioRef} autoPlay className="remote-call-audio" />
            <div className={`call-orb ${voice?.state || "active"}`}><PhoneCall size={34} /><strong>{voice?.state === "ended" ? "Call complete" : voice?.held ? "On hold" : sipStatus === "calling" ? "Calling" : "Connected"}</strong><span>{selected.language.toUpperCase()} · {window.platformRuntime?.sip?.enabled ? "live Asterisk WebRTC" : voice?.provider.replaceAll("_", " ")}</span></div>
            {voice?.state !== "ended" && <div className="call-controls"><button aria-label={voice?.muted ? "Unmute" : "Mute"} onClick={() => void control(voice?.muted ? "unmute" : "mute")}><MicOff size={18} /><span>{voice?.muted ? "Unmute" : "Mute"}</span></button><button aria-label={voice?.held ? "Resume" : "Hold"} onClick={() => void control(voice?.held ? "resume" : "hold")}>{voice?.held ? <Play size={18} /> : <Pause size={18} />}<span>{voice?.held ? "Resume" : "Hold"}</span></button><button aria-label="Transfer" onClick={() => void control("transfer", "1002")}><UsersRound size={18} /><span>Transfer</span></button><button className="hangup" aria-label="Hang up" onClick={() => void control("hangup")}><PhoneOff size={18} /><span>Hang up</span></button></div>}
            {!!transcript.length && <div className="transcript-panel"><div className="transcript-head"><div><span className="section-kicker">SYNCHRONIZED TRANSCRIPT</span><strong>Speaker-aware conversation</strong></div>{recordingUrl && <audio aria-label="Call recording" controls src={recordingUrl} onTimeUpdate={(event) => setPlayhead(event.currentTarget.currentTime * 1000)} />}</div>{transcript.map((segment) => <button key={segment.id} className={`transcript-row ${playhead >= segment.start_ms && playhead <= segment.end_ms ? "playing" : ""}`}><span>{segment.speaker}</span><p>{segment.text}</p><time>{Math.floor(segment.start_ms / 60000)}:{String(Math.floor(segment.start_ms / 1000) % 60).padStart(2, "0")}</time></button>)}</div>}
          </div>}
          {error && <div className="inline-error">{error}</div>}
        </> : <div className="no-conversation dial-state"><div><PhoneCall size={34} /></div><h2>Start a voice interaction</h2><p>{window.platformRuntime?.sip?.enabled ? "Dial extension 2003 for a real two-party WebRTC proof with customer endpoint 1003." : "Process a prerecorded multilingual call through the configured AI route."}</p><form onSubmit={dial} className="dial-form"><input aria-label="Customer phone" value={phone} onChange={(event) => setPhone(event.target.value)} /><select aria-label="Call language" value={callLanguage} onChange={(event) => setCallLanguage(event.target.value)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="mr">मराठी · review required</option><option value="hi-en">Hinglish</option><option value="auto">Auto detect · uploaded/live audio</option></select><button aria-label="Start call"><PhoneCall size={18} /> {window.platformRuntime?.sip?.enabled ? "Call extension" : "Start AI sample"}</button></form></div>}
      </section>
      <aside className="assist-panel"><div className="assist-title"><div><Sparkles size={17} /></div><span>LIVE ASSIST</span><i /></div><div className="assist-card primary"><span>{currentAssist?.event_type.replaceAll("_", " ").toUpperCase() || "NEXT BEST ACTION"}</span><strong>{currentAssist?.content || (selected ? "Listen actively and follow the configured campaign steps." : "Guidance appears when an interaction is active.")}</strong><small>{currentAssist?.title || "Campaign playbook"} · {String(currentAssist?.metadata?.source || "configured AI").replaceAll("_", " ")}</small></div><div className="checklist"><div className="checklist-head"><span>Configured call flow</span><b>{transcript.length ? "Evidence active" : "Not started"}</b></div>{["Professional greeting", "Understand the caller task", "Give the source-backed answer", "Offer further help", "Close professionally"].map((step) => <label key={step}><i />{step}</label>)}</div><div className="knowledge-card"><BookOpen size={17} /><div><span>KNOWLEDGE</span><strong>{currentKnowledge?.content || "Contextual policy guidance appears here."}</strong></div></div><div className="privacy-note"><ShieldCheck size={15} /> Processing mode: <b>{voice ? (voice.provider === "groq_external" ? "External Groq" : "Strict local") : "Configured AI route"}</b></div></aside>
    </div>
  </div>;
}

function CustomerWidget() {
  const [name, setName] = useState(""); const [first, setFirst] = useState(""); const [language, setLanguage] = useState("en");
  const [chat, setChat] = useState<{ id: string; session: string } | null>(null); const [messages, setMessages] = useState<ChatMessage[]>([]); const [draft, setDraft] = useState(""); const [error, setError] = useState(""); const [chatStatus, setChatStatus] = useState("active"); const [rating, setRating] = useState<number | null>(null);
  async function start(event: FormEvent) { event.preventDefault(); try { const result = await api.startChat(name, first, language); setChat({ id: result.conversation_id, session: result.session_token }); setMessages(await api.customerMessages(result.conversation_id, result.session_token)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start chat"); } }
  async function send(event: FormEvent) { event.preventDefault(); if (!chat || !draft.trim()) return; await api.sendCustomerMessage(chat.id, chat.session, draft.trim()); setDraft(""); setMessages(await api.customerMessages(chat.id, chat.session)); }
  async function rate(value: number) { if (!chat) return; await api.submitSurvey(chat.id, chat.session, value); setRating(value); }
  useEffect(() => { if (!chat) return; const timer = window.setInterval(async () => { try { const [nextMessages, status] = await Promise.all([api.customerMessages(chat.id, chat.session), api.customerStatus(chat.id, chat.session)]); setMessages(nextMessages); setChatStatus(status.status); setRating(status.actual_csat); } catch { /* A transient poll failure must not break the customer session. */ } }, 2000); return () => clearInterval(timer); }, [chat]);
  return <main className="widget-page"><section className="widget-card"><header><div className="widget-logo"><Waveform size={19} /></div><div><strong>Aperture Support</strong><span><i /> Support channel ready</span></div></header>{!chat ? <form onSubmit={start} className="widget-start"><div><span className="section-kicker">PRIVATE SUPPORT</span><h1>How can we help?</h1><p>Start a secure conversation with our team.</p></div><label>Your name<input aria-label="Your name" required value={name} onChange={(e) => setName(e.target.value)} /></label><label>Language<select aria-label="Preferred language" value={language} onChange={(e) => setLanguage(e.target.value)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="mr">मराठी</option><option value="hi-en">Hinglish</option></select></label><label>Message<textarea aria-label="Initial message" required value={first} onChange={(e) => setFirst(e.target.value)} placeholder="Tell us what you need help with…" /></label>{error && <div className="form-error">{error}</div>}<button className="primary-button">Start conversation <ChevronRight size={18} /></button></form> : <div className="widget-chat"><div className="widget-status"><span>{chatStatus === "closed" ? "Conversation resolved" : "Connected to support"}</span><StatusPill status={chatStatus} /></div><div className="message-stream">{messages.map((message) => <div className={`message ${message.sender_type}`} key={message.id}><span>{message.sender_type === "customer" ? "You" : "Support"}</span><p>{message.content}</p><time>{formatTime(message.created_at)}</time></div>)}</div>{chatStatus === "closed" ? <div className="survey-card"><span>How was your support experience?</span><div>{[1, 2, 3, 4, 5].map((value) => <button aria-label={`Rate ${value}`} className={rating === value ? "selected" : ""} onClick={() => void rate(value)} key={value}>{value}</button>)}</div>{rating && <small>Thank you. Your recorded CSAT is {rating}/5.</small>}</div> : <form onSubmit={send} className="composer"><input aria-label="Reply" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Type your reply…" /><button aria-label="Send"><Send size={18} /></button></form>}</div>}<footer><ShieldCheck size={14} /> Secured by the on-prem contact centre</footer></section></main>;
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
  let content;
  if (isAgent) content = <AgentView token={auth.token} user={auth.user} assigned={conversations} queued={queued} onRefresh={() => void refresh()} />;
  else if (page === "conversations") content = <ConversationExplorer token={auth.token} conversations={conversations} />;
  else if (page === "intelligence") content = <IntelligenceView token={auth.token} />;
  else if (page === "quality") content = <QualityView token={auth.token} canReview={auth.user.role !== "client_viewer"} />;
  else if (page === "coaching") content = <CoachingView token={auth.token} user={auth.user} />;
  else if (page === "reports") content = <ReportsView token={auth.token} user={auth.user} />;
  else if (page === "settings") content = <ConfigurationView token={auth.token} admin={auth.user.role === "admin"} />;
  else content = <SupervisorView token={auth.token} user={auth.user} conversations={conversations} agents={agents} summary={summary} refresh={() => void refresh()} />;
  return <div className="app-frame"><Sidebar user={auth.user} page={page} onPage={setPage} onLogout={logout} /><main className="main-canvas">{content}</main></div>;
}
