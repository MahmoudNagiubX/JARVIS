const app = document.querySelector("#app");

const view = {
  session: null,
  state: null,
  health: null,
  profile: null,
  conversations: [],
  selectedConversation: null,
  messages: [],
  memory: [],
  research: [],
  context: null,
  route: routeFromLocation(),
  error: "",
  loading: true,
  sending: false,
  paletteOpen: false,
  modal: null,
};

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function routeFromLocation() {
  return (window.location.hash.replace(/^#\/?/, "").split("/")[0] || "home");
}

function array(value) {
  return Array.isArray(value) ? value : [];
}

function text(value, fallback = "Not available") {
  const result = String(value ?? "").trim();
  return result || fallback;
}

function formatDate(value) {
  if (!value) return "No timestamp";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? text(value) : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function formatShortDate(value) {
  if (!value) return "No timestamp";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? text(value) : date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function titleCase(value) {
  return text(value, "unknown").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function tone(value) {
  const lowered = text(value, "").toLowerCase();
  if (["ready", "idle", "completed", "succeeded", "online", "available", "connected", "pass"].includes(lowered)) return "good";
  if (["degraded", "paused", "pending", "waiting", "approval_required", "offline", "unavailable", "unknown"].includes(lowered)) return "warn";
  if (["error", "failed", "cancelled", "revoked", "unhealthy"].includes(lowered)) return "bad";
  return "";
}

function badge(value) {
  return `<span class="badge ${tone(value)}">${escapeHTML(titleCase(value))}</span>`;
}

function emptyState(message, detail = "") {
  return `<div class="empty"><strong>${escapeHTML(message)}</strong>${detail ? `<br><span>${escapeHTML(detail)}</span>` : ""}</div>`;
}

function rows(values) {
  return `<div class="status-list">${Object.entries(values).map(([label, value]) => `<div class="status-row"><span>${escapeHTML(label)}</span><span class="status-value ${tone(value)}">${escapeHTML(text(value))}</span></div>`).join("")}</div>`;
}

function ownerQuery(path, extra = "") {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}owner_id=${encodeURIComponent(view.session.owner_id)}${extra}`;
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && typeof options.body === "object") {
    headers.set("Content-Type", "application/json");
    options = { ...options, body: JSON.stringify(options.body) };
  }
  if (view.session?.csrf_token && options.method && options.method !== "GET") {
    headers.set("X-JARVIS-CSRF", view.session.csrf_token);
  }
  const response = await fetch(`/v1${path}`, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      detail = text(payload.error, detail);
    } catch (_) {
      // Keep the UI error bounded when a local service returns no JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return {};
  return response.json();
}

async function establishSession() {
  const hash = window.location.hash;
  const match = hash.match(/^#\/?.*?bootstrap=([^&]+)/);
  if (match) {
    view.session = await request("/auth/desktop-session", { method: "POST", body: { bootstrap: decodeURIComponent(match[1]) } });
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  } else {
    view.session = await request("/auth/session");
  }
}

async function refreshState(shouldRender = true) {
  const previous = JSON.stringify(view.state);
  view.state = await request(ownerQuery("/experience/state"));
  if (shouldRender && previous !== JSON.stringify(view.state)) render();
}

async function refreshConversations() {
  const payload = await request(ownerQuery("/conversations"));
  view.conversations = array(payload.conversations);
  if (view.selectedConversation && !view.conversations.some((item) => item.id === view.selectedConversation)) {
    view.selectedConversation = null;
  }
}

async function loadMessages() {
  if (!view.selectedConversation) {
    view.messages = [];
    return;
  }
  const payload = await request(ownerQuery(`/conversations/${encodeURIComponent(view.selectedConversation)}/messages`));
  view.messages = array(payload.messages);
}

async function loadRouteData() {
  view.error = "";
  try {
    if (view.route === "chat") {
      await refreshConversations();
      await loadMessages();
    } else if (view.route === "memory") {
      const payload = await request(ownerQuery("/memory", "&limit=50"));
      view.memory = array(payload.memories);
    } else if (view.route === "research") {
      const payload = await request("/research/runs");
      view.research = array(payload.runs);
    } else if (view.route === "context") {
      view.context = await request("/context");
    } else if (view.route === "settings") {
      view.health = await request("/health");
      view.profile = await request(ownerQuery("/personalization/profile"));
    }
  } catch (error) {
    view.error = error instanceof Error ? error.message : "The local service is unavailable.";
  }
  render();
}

function navButton(route, label, icon, count = 0) {
  return `<button class="nav-button ${view.route === route ? "active" : ""}" data-route="${route}" aria-current="${view.route === route ? "page" : "false"}"><span>${icon} &nbsp;${escapeHTML(label)}</span>${count ? `<span class="nav-badge">${count}</span>` : ""}</button>`;
}

function header() {
  const system = view.state?.system || {};
  const status = text(view.state?.state, "offline");
  const local = system.offline ? "LOCAL" : "ONLINE";
  const model = system.model_available ? "MODEL READY" : "MODEL OFFLINE";
  return `<header class="topbar"><div class="brand"><span class="brand-mark" aria-hidden="true"></span><div><div class="brand-name">J.A.R.V.I.S.</div><div class="brand-subtitle">Personal operating assistant</div></div></div><div class="topbar-state"><span class="state-dot ${tone(status)}" aria-hidden="true"></span><strong>${escapeHTML(titleCase(status))}</strong><span>${escapeHTML(local)}</span><span>${escapeHTML(model)}</span><button class="button ghost" data-palette aria-label="Open command palette">Ctrl K</button></div></header>`;
}

function sidebar() {
  const state = view.state || {};
  const approvals = array(state.approvals).filter((item) => text(item.status, "pending") === "pending").length;
  const missions = array(state.missions).filter((item) => ["running", "waiting", "waiting_approval"].includes(text(item.status, ""))).length;
  return `<aside class="sidebar"><div class="nav-group"><div class="nav-label">Workspace</div><div class="nav-list">${navButton("home", "Home", "[ ]")}${navButton("chat", "Chat", ">_")}${navButton("missions", "Missions", "[=]", missions)}${navButton("memory", "Memory", "[M]")}${navButton("context", "Current context", "[C]")}</div></div><div class="nav-group"><div class="nav-label">Capabilities</div><div class="nav-list">${navButton("automation", "Automation", "[A]")}${navButton("research", "Research", "[R]")}${navButton("engineering", "Engineering", "[E]")}${navButton("browser", "Browser", "[B]")}${navButton("skills", "Skills", "[S]")}${navButton("devices", "Devices", "[D]")}${navButton("notifications", "Notifications", "[N]")}</div></div><div class="nav-group"><div class="nav-label">Control</div><div class="nav-list">${navButton("approvals", "Approvals", "!", approvals)}${navButton("activity", "Activity", "[+] ")}${navButton("settings", "Settings", "[*]")}</div></div><div class="sidebar-footer">LOCAL-FIRST<br>Real state. Safe actions.<br><span class="codeish">Ctrl+K</span> command palette</div></aside>`;
}

function pageHeading(eyebrow, title, description = "", action = "") {
  return `<div class="page-heading"><div><p class="eyebrow">${escapeHTML(eyebrow)}</p><h1>${escapeHTML(title)}</h1>${description ? `<p class="lede">${escapeHTML(description)}</p>` : ""}</div>${action}</div>`;
}

function metric(label, value, state = "") {
  return `<div class="metric"><div class="metric-label">${escapeHTML(label)}</div><div class="metric-value ${state}">${escapeHTML(text(value))}</div></div>`;
}

function corePanel() {
  const state = text(view.state?.state, "offline");
  const active = !["idle", "offline", "degraded"].includes(state);
  const system = view.state?.system || {};
  return `<section class="panel core-panel ${active ? "is-active" : ""}"><div class="core-orb" aria-hidden="true"></div><div class="core-label"><div class="core-state">${escapeHTML(titleCase(state))}</div><div class="core-detail">${escapeHTML(system.offline ? "Local mode · internet unavailable" : "Local runtime connected")}</div></div></section>`;
}

function healthPanel() {
  const system = view.state?.system || {};
  const voice = view.state?.voice || {};
  return `<section class="panel accent-panel"><div class="panel-head"><h2>Runtime status</h2>${badge(system.offline ? "local" : "online")}</div><div class="metric-grid">${metric("Local brain", system.model_available ? system.model_alias || "Ready" : "Unavailable", system.model_available ? "good" : "bad")}${metric("Voice", voice.state || "No active session", tone(voice.state))}${metric("Devices", array(view.state?.devices).length, "")}${metric("Approvals", array(view.state?.approvals).length, array(view.state?.approvals).length ? "warn" : "good")}</div><div style="height:14px"></div>${rows({"Runtime": titleCase(system.runtime_state), "Provider": system.model_provider || "None", "Network": system.offline ? "Offline · local features remain available" : "Online", "Generated": formatDate(view.state?.generated_at)})}</section>`;
}

function approvalsBlock() {
  const approvals = array(view.state?.approvals).filter((item) => text(item.status, "pending") === "pending");
  if (!approvals.length) return emptyState("No pending approvals.", "JARVIS will surface consequential actions here.");
  const runs = array(view.state?.runs);
  return `<div class="item-list">${approvals.map((approval) => {
    const run = runs.find((candidate) => candidate.pending_approval_id === approval.approval_id);
    return `<div class="approval-card"><div class="approval-title">Approval required</div><div class="approval-action">${escapeHTML(text(approval.action, "Consequential action"))}</div><div class="approval-reason">${escapeHTML(text(approval.reason, "The action requires owner confirmation."))}</div><div class="button-row"><button class="button primary" data-approval="${escapeHTML(approval.approval_id)}" data-run="${escapeHTML(run?.run_id || "")}" data-approved="true" ${run ? "" : "disabled"}>Approve</button><button class="button danger" data-approval="${escapeHTML(approval.approval_id)}" data-run="${escapeHTML(run?.run_id || "")}" data-approved="false" ${run ? "" : "disabled"}>Deny</button></div></div>`;
  }).join("")}</div>`;
}

function activityBlock(limit = 6) {
  const events = array(view.state?.timeline).slice(-limit).reverse();
  if (!events.length) return emptyState("No activity yet.", "Real runtime events will appear here.");
  return `<div class="event-list">${events.map((event) => `<div class="event-row"><span class="event-time">${escapeHTML(formatShortDate(event.timestamp))}</span><div class="event-text">${escapeHTML(titleCase(event.event_type))}<small>${escapeHTML(titleCase(event.state))} · ${escapeHTML(event.category || "system")}</small></div></div>`).join("")}</div>`;
}

function homePage() {
  const state = view.state || {};
  const presence = state.presence || {};
  const home = state.home || {};
  return `<div class="page">${pageHeading("Command Center", "Good to see you.", "One coherent view of your local JARVIS runtime, current work, and attention queue.", `<button class="button primary" data-route="chat">New chat</button>`)}<div class="hero-grid">${corePanel()}${healthPanel()}</div><div class="grid grid-3"><section class="panel"><div class="panel-head"><h2>What needs attention</h2><span class="muted">${array(state.approvals).length} pending</span></div>${approvalsBlock()}</section><section class="panel"><div class="panel-head"><h2>Current context</h2><span class="muted">${escapeHTML(text(presence.source, "Live projection"))}</span></div>${rows({"Active app": presence.active_application || presence.active_app || "Not observed", "Focused window": presence.focused_window || "Not observed", "Workspace": presence.current_workspace || "Not observed", "Home": home.available ? "Connected" : "No live controller"})}</section><section class="panel"><div class="panel-head"><h2>Active work</h2><span class="muted">${array(state.missions).length} missions</span></div>${array(state.missions).length ? `<div class="item-list">${array(state.missions).slice(0, 4).map((item) => `<div class="list-row"><div><h3>${escapeHTML(text(item.title, item.request || "Untitled mission"))}</h3><span class="small muted">${escapeHTML(text(item.current_step, "No active step"))}</span></div><span>${badge(item.status)}</span></div>`).join("")}</div>` : emptyState("No active missions.", "Create one through the existing mission service.")}</section></div><div class="grid grid-2" style="margin-top:15px"><section class="panel"><div class="panel-head"><h2>Recent activity</h2><button class="button ghost" data-route="activity">View all</button></div>${activityBlock()}</section><section class="panel"><div class="panel-head"><h2>Quick health</h2><span class="muted">authoritative state</span></div>${rows({"Goals": array(state.goals).length, "Memory": "Inspectable", "Research": array(state.research).length, "Voice acceptance": "Deferred by design"})}</section></div></div>`;
}

function conversationButton(item) {
  return `<button class="conversation-button ${view.selectedConversation === item.id ? "active" : ""}" data-conversation="${escapeHTML(item.id)}"><span class="conversation-title">${escapeHTML(text(item.title, "Untitled conversation"))}</span><span class="conversation-date">${escapeHTML(formatShortDate(item.updated_at || item.last_message_at))}</span></button>`;
}

function messageBlock(item) {
  const role = item.role === "user" ? "You" : titleCase(item.role);
  return `<article class="message ${item.role === "user" ? "user" : "assistant"}"><span class="message-role">${escapeHTML(role)}</span>${escapeHTML(item.content)}<span class="message-meta">${escapeHTML(formatDate(item.created_at))}</span></article>`;
}

function chatPage() {
  const messages = view.messages.length ? view.messages.map(messageBlock).join("") : `<div class="empty">Start a conversation with the local JARVIS brain.<br><span>Text uses the same AgentRuntime, context, tools, and approval authority as voice.</span></div>`;
  return `<div class="page">${pageHeading("Conversation", "Chat with JARVIS", "A text-first path to the same local brain. Voice acceptance can remain deferred without blocking daily use.")}<div class="chat-layout"><section class="panel compact"><div class="panel-head"><h2>Conversations</h2><button class="button ghost" data-new-chat>New</button></div><div class="conversation-list">${view.conversations.length ? view.conversations.map(conversationButton).join("") : emptyState("No saved conversations.", "Your first message creates one.")}</div></section><section class="panel chat-panel"><div class="panel-head"><div><h2>${escapeHTML(view.selectedConversation ? (view.conversations.find((item) => item.id === view.selectedConversation)?.title || "Conversation") : "New conversation")}</h2><span class="muted">Same local AgentRuntime · no cloud UI dependency</span></div>${view.error ? `<span class="badge bad">${escapeHTML(view.error)}</span>` : ""}</div><div class="message-list" aria-live="polite">${messages}${view.sending ? `<div class="message assistant"><span class="message-role">JARVIS</span>Working from the local runtime...</div>` : ""}</div><form class="composer" data-chat-form><textarea name="message" placeholder="Ask JARVIS anything local..." aria-label="Message JARVIS" required></textarea><button class="button primary" type="submit" ${view.sending ? "disabled" : ""}>${view.sending ? "Working" : "Send"}</button></form></section></div></div>`;
}

function missionsPage() {
  const missions = array(view.state?.missions);
  return `<div class="page">${pageHeading("Operations", "Missions & goals", "Inspect bounded work already owned by the mission and goal services.")}<div class="grid grid-2">${missions.length ? missions.map((item) => `<section class="panel"><div class="panel-head"><h2>${escapeHTML(text(item.title, item.request || "Untitled mission"))}</h2>${badge(item.status)}</div>${rows({"Goal": item.goal_id || "None", "Current step": item.current_step || "Not started", "Updated": formatDate(item.updated_at), "Budget": item.budget ? "Bounded" : "Not reported"})}</section>`).join("") : `<section class="panel">${emptyState("No missions recorded.", "Production state is empty until the canonical mission service creates work.")}</section>`}</div></div>`;
}

function automationPage() {
  const automations = array(view.state?.automations);
  return `<div class="page">${pageHeading("Personal operations", "Automation", "Inspectable recurring rules from the canonical automation service. Actions and risk remain policy-controlled.")}<div class="grid grid-2">${automations.length ? automations.map((item) => `<section class="panel"><div class="panel-head"><h2>${escapeHTML(text(item.name, item.rule_id || "Automation rule"))}</h2>${badge(item.enabled ? "enabled" : "paused")}</div>${rows({"Trigger": item.trigger?.value || item.trigger?.kind || "Not reported", "Risk": item.risk_level || "Not reported", "Cooldown": item.cooldown_seconds ? `${item.cooldown_seconds}s` : "Not reported", "Actions": array(item.actions).length || "Not reported"})}</section>`).join("") : `<section class="panel">${emptyState("No automations configured.", "Create recurring work through the canonical operations and automation services.")}</section>`}</div></div>`;
}

function engineeringPage() {
  const sessions = array(view.state?.engineering);
  return `<div class="page">${pageHeading("Developer workers", "Engineering", "Read-only worker and engineering-session state. Subscription-backed coding agents remain development-only and are not runtime dependencies.")}<div class="grid grid-2">${sessions.length ? sessions.map((item) => `<section class="panel"><div class="panel-head"><h2>${escapeHTML(text(item.provider, item.session_id || "Engineering session"))}</h2>${badge(item.status)}</div>${rows({"Session": item.session_id, "Last action": item.last_action || "Not reported", "Artifacts": item.artifact_count ?? "Not reported"})}</section>`).join("") : `<section class="panel">${emptyState("No active engineering workers.", "Worker state appears when the existing engineering service creates a session.")}</section>`}</div></div>`;
}

function browserPage() {
  return `<div class="page">${pageHeading("Safe capability surface", "Browser", "Browser work remains behind the existing browser authority and approval policy.")}<section class="panel"><div class="panel-head"><h2>No live browser job</h2>${badge("offline")}</div>${emptyState("No browser controller is connected.", "Use Chat for a natural request when the existing browser adapter is configured. JARVIS will show approval and progress from real backend events; it will not fabricate a browser session.")}</section></div>`;
}

function memoryCard(item) {
  const id = item.memory_id || item.id;
  return `<article class="panel compact"><div class="panel-head"><div><span class="badge">${escapeHTML(text(item.category, "memory"))}</span><h3 style="margin-top:8px">${escapeHTML(text(item.content, "Empty memory"))}</h3></div><span class="small muted">${escapeHTML(formatShortDate(item.updated_at || item.created_at))}</span></div>${rows({"Source": item.source || item.source_reference || "Unknown", "Confidence": item.confidence ?? "Not reported", "Sensitivity": item.sensitivity || "Not reported"})}<div class="button-row" style="margin-top:13px"><button class="button ghost" data-edit-memory="${escapeHTML(id)}">Edit</button><button class="button danger" data-delete-memory="${escapeHTML(id)}">Delete</button></div></article>`;
}

function memoryPage() {
  return `<div class="page">${pageHeading("Personal knowledge", "Memory center", "Inspect, edit, and delete durable accepted knowledge. Current world observations remain separate.")}<section class="panel" style="margin-bottom:15px"><form class="composer" data-memory-form><input class="search-input" name="query" value="" placeholder="Search memories by text, category, or source" aria-label="Search memories"><button class="button primary" type="submit">Search</button></form></section><div class="grid grid-2">${view.memory.length ? view.memory.map(memoryCard).join("") : `<section class="panel">${emptyState("No memories found.", "Memory remains empty until the canonical MemoryService accepts a record.")}</section>`}</div></div>`;
}

function contextPage() {
  const state = view.state || {};
  const context = view.context || {};
  const world = context.world_state || context.world || state.home || {};
  return `<div class="page">${pageHeading("Live projection", "Current context", "Fresh, bounded observations from the existing perception, presence, workspace, and world-state services. Nothing here is silently persisted as memory.")}<div class="grid grid-2"><section class="panel"><div class="panel-head"><h2>Desktop and presence</h2><span class="muted">source-owned</span></div>${rows({"Active device": state.presence?.active_device_id || "Not observed", "Active application": state.presence?.active_application || "Not observed", "Focused window": state.presence?.focused_window || "Not observed", "Current session": state.conversation?.session_id || "No active session", "Freshness": context.generated_at ? formatDate(context.generated_at) : "Projection refresh"})}</section><section class="panel"><div class="panel-head"><h2>World state</h2><span class="muted">bounded facts</span></div>${Object.keys(world).length ? rows(Object.fromEntries(Object.entries(world).slice(0, 9).map(([key, value]) => [key, typeof value === "object" ? JSON.stringify(value) : value]))) : emptyState("No fresh world-state facts.", "JARVIS will show observations when an approved provider reports them.")}</section></div><section class="panel" style="margin-top:15px"><div class="panel-head"><h2>Home context</h2>${badge(state.home?.available ? "connected" : "offline")}</div>${rows({"Controller": state.home?.available ? "Live controller connected" : "No live home controller connected", "Entities": state.home?.entities?.length ?? 0, "Policy": "No fake devices"})}</section></div>`;
}

function researchPage() {
  return `<div class="page">${pageHeading("Evidence ledger", "Research", "Existing research runs and evidence status. Web capability remains explicit when the provider is unavailable.")}<div class="grid grid-2">${view.research.length ? view.research.map((item) => `<section class="panel"><div class="panel-head"><h2>${escapeHTML(text(item.query, "Research run"))}</h2>${badge(item.status)}</div>${rows({"Created": formatDate(item.created_at), "Completed": formatDate(item.completed_at), "Sources": item.source_count ?? "Not reported", "Error": item.error_code || "None"})}</section>`).join("") : `<section class="panel">${emptyState("No research runs.", "Start a request through the existing ResearchService when a provider is configured.")}</section>`}</div></div>`;
}

function skillsPage() {
  const skills = array(view.state?.skills);
  return `<div class="page">${pageHeading("Capability registry", "Skills", "Installed skill metadata from the product-owned registry. Enablement and execution remain policy-controlled.")}<div class="grid grid-3">${skills.length ? skills.map((item) => `<section class="panel compact"><div class="panel-head"><h2>${escapeHTML(text(item.name, item.skill_id || "Skill"))}</h2>${badge(item.status)}</div><p class="muted small">${escapeHTML(text(item.description, "No description"))}</p>${rows({"Version": item.version || item.current_version || "Not reported", "Risk": item.risk_level || "Not reported", "Source": item.source || "Product registry"})}</section>`).join("") : `<section class="panel">${emptyState("No skills installed.", "The registry is the source of truth; no fixture skills are shown.")}</section>`}</div></div>`;
}

function devicesPage() {
  const devices = array(view.state?.devices);
  return `<div class="page">${pageHeading("Device fabric", "Devices & home", "Actual registered device and home-controller state. Venom and physical home devices are never marked live without evidence.")}<div class="grid grid-2">${devices.length ? devices.map((item) => `<section class="panel"><div class="panel-head"><h2>${escapeHTML(text(item.name, item.device_id || "Device"))}</h2>${badge(item.status)}</div>${rows({"Device": item.device_id, "Last seen": formatDate(item.last_seen), "Capabilities": array(item.capabilities).join(", ") || "None reported", "Role": item.role || "Not reported"})}</section>`).join("") : `<section class="panel">${emptyState("No registered devices.", "Connect a device through the canonical device authority.")}</section>`}</div><section class="panel" style="margin-top:15px">${emptyState("No live home controller connected.", "Home integration will appear here when configured.")}</section></div>`;
}

function notificationsPage() {
  const notifications = array(view.state?.notifications);
  return `<div class="page">${pageHeading("Owner attention", "Notifications", "Unread, proactive, and system notices projected from the existing notification service.")}<section class="panel"><div class="item-list">${notifications.length ? notifications.map((item) => `<div class="list-row"><div style="min-width:0;flex:1"><h3>${escapeHTML(text(item.title, "Notification"))}</h3><p class="small muted">${escapeHTML(text(item.message, ""))}</p><span class="small muted">${escapeHTML(formatDate(item.created_at))}</span></div>${badge(item.dismissed ? "dismissed" : item.severity || "info")}</div>`).join("") : emptyState("No notifications.", "JARVIS will surface important changes here without spam.")}</div></section></div>`;
}

function approvalsPage() {
  return `<div class="page">${pageHeading("Owner control", "Approval center", "Exact consequential actions are shown from the approval authority. JARVIS never invents risk levels or previews secrets.")}<section class="panel">${approvalsBlock()}</section></div>`;
}

function activityPage() {
  return `<div class="page">${pageHeading("Audit projection", "Activity", "A readable owner-facing timeline separate from low-level logs. Sensitive payloads are redacted before reaching the experience projection.")}<section class="panel">${activityBlock(100)}</section></div>`;
}

function settingsPage() {
  const health = view.health || {};
  const model = health.local_model || health.model || {};
  const voice = view.state?.voice || {};
  return `<div class="page">${pageHeading("Configuration", "Settings & health", "Operational status and privacy controls remain grounded in the current local runtime.")}<div class="grid grid-2"><section class="panel"><div class="panel-head"><h2>System health</h2>${badge(health.state || view.state?.state)}</div>${rows({"Core": health.state || "Not reported", "Database": health.database || "Not reported", "Local model": model.available ? "Ready" : "Unavailable", "Provider": model.provider || "Not reported", "Voice": voice.state || "No active voice session", "Venom": health.venom?.status || "Not connected"})}</section><section class="panel"><div class="panel-head"><h2>Privacy center</h2><span class="muted">local policy</span></div>${rows({"Raw audio stored": "NO", "Raw screenshots stored": "NO", "Core cloud dependency": "NO", "Memory": "Inspectable / editable / deletable", "Credentials": "HttpOnly session boundary"})}<div class="notice" style="margin-top:14px">Physical voice acceptance is intentionally deferred to the final acceptance phase. Normal voice operational state remains visible when the backend reports it.</div></section></div><section class="panel" style="margin-top:15px"><div class="panel-head"><h2>Advanced diagnostics</h2><span class="muted">legacy repair path retained</span></div>${emptyState("Desktop setup and audio repair remain available from the existing Tk lifecycle window.", "The Command Center does not replace the known-working local repair path.")}</section></div>`;
}

function page() {
  switch (view.route) {
    case "chat": return chatPage();
    case "missions": return missionsPage();
    case "automation": return automationPage();
    case "engineering": return engineeringPage();
    case "browser": return browserPage();
    case "memory": return memoryPage();
    case "context": return contextPage();
    case "research": return researchPage();
    case "skills": return skillsPage();
    case "devices": return devicesPage();
    case "notifications": return notificationsPage();
    case "approvals": return approvalsPage();
    case "activity": return activityPage();
    case "settings": return settingsPage();
    default: return homePage();
  }
}

function palette() {
  if (!view.paletteOpen) return "";
  const query = view.paletteQuery || "";
  const haystack = [
    ...array(view.conversations).map((item) => ({ type: "Conversation", label: text(item.title, "Untitled conversation"), route: "chat" })),
    ...array(view.state?.missions).map((item) => ({ type: "Mission", label: text(item.title, item.request), route: "missions" })),
    ...array(view.memory).map((item) => ({ type: "Memory", label: text(item.content), route: "memory" })),
    ...["Home", "Chat", "Missions", "Memory", "Current context", "Automation", "Research", "Engineering", "Browser", "Skills", "Devices", "Notifications", "Approvals", "Activity", "Settings"].map((label) => ({ type: "Page", label, route: label.toLowerCase().replace(" ", "-") })),
  ];
  const results = haystack.filter((item) => item.label.toLowerCase().includes(query.toLowerCase())).slice(0, 12);
  return `<div class="modal-backdrop" data-close-palette><section class="modal palette" role="dialog" aria-modal="true" aria-label="Command palette"><div class="field"><label for="palette-input">Search local JARVIS</label><input id="palette-input" class="search-input" value="${escapeHTML(query)}" data-palette-input autofocus placeholder="Search pages, conversations, missions, memories"></div><div class="palette-results">${results.length ? results.map((item) => `<button class="palette-item" data-palette-route="${escapeHTML(item.route)}"><span class="palette-type">${escapeHTML(item.type)}</span><span>${escapeHTML(item.label)}</span></button>`).join("") : emptyState("No local matches.")}</div></section></div>`;
}

function memoryModal() {
  if (!view.modal) return "";
  return `<div class="modal-backdrop" data-close-modal><section class="modal" role="dialog" aria-modal="true" aria-label="Edit memory"><h2>Edit memory</h2><form data-memory-edit><div class="field"><label for="memory-content">Content</label><textarea id="memory-content" name="content" rows="6" required>${escapeHTML(view.modal.content)}</textarea></div><div class="button-row"><button class="button primary" type="submit">Save memory</button><button class="button ghost" type="button" data-close-modal>Cancel</button></div></form></section></div>`;
}

function render() {
  if (!view.session) {
    app.innerHTML = `<section class="fatal-screen"><div class="boot-orb"></div><h1>JARVIS is waiting for a local session</h1><p>Open the Command Center from the desktop launcher.</p></section>`;
    return;
  }
  if (view.loading) {
    app.innerHTML = `<section class="boot-screen"><div class="boot-orb"></div><p>Rebuilding authoritative local state...</p></section>`;
    return;
  }
  const approvals = array(view.state?.approvals).filter((item) => text(item.status, "pending") === "pending").length;
  app.innerHTML = `<div class="app-shell">${header()}<div class="layout">${sidebar()}<main class="main">${view.error && view.route !== "chat" ? `<div class="notice error" style="margin-bottom:15px">${escapeHTML(view.error)}</div>` : ""}${page()}</main></div></div>${palette()}${memoryModal()}`;
  document.querySelectorAll("[data-route]").forEach((element) => element.addEventListener("click", () => navigate(element.dataset.route)));
  document.querySelector("[data-palette]")?.addEventListener("click", openPalette);
  document.querySelector("[data-new-chat]")?.addEventListener("click", () => { view.selectedConversation = null; view.messages = []; navigate("chat"); });
  document.querySelectorAll("[data-conversation]").forEach((element) => element.addEventListener("click", async () => {
    view.selectedConversation = element.dataset.conversation;
    await loadMessages();
    render();
  }));
  document.querySelector("[data-chat-form]")?.addEventListener("submit", submitMessage);
  document.querySelector("[data-memory-form]")?.addEventListener("submit", searchMemory);
  document.querySelectorAll("[data-delete-memory]").forEach((element) => element.addEventListener("click", () => deleteMemory(element.dataset.deleteMemory)));
  document.querySelectorAll("[data-edit-memory]").forEach((element) => element.addEventListener("click", () => editMemory(element.dataset.editMemory)));
  document.querySelectorAll("[data-approval]").forEach((element) => element.addEventListener("click", () => decideApproval(element)));
  document.querySelectorAll("[data-palette-route]").forEach((element) => element.addEventListener("click", () => { view.paletteOpen = false; navigate(element.dataset.paletteRoute); }));
  document.querySelector("[data-palette-input]")?.addEventListener("input", (event) => { view.paletteQuery = event.target.value; render(); document.querySelector("[data-palette-input]")?.focus(); });
  document.querySelector("[data-close-palette]")?.addEventListener("click", (event) => { if (event.target === event.currentTarget) { view.paletteOpen = false; render(); } });
  document.querySelectorAll("[data-close-modal]").forEach((element) => element.addEventListener("click", (event) => { if (event.target === element || element.dataset.closeModal !== undefined) { view.modal = null; render(); } }));
  document.querySelector("[data-memory-edit]")?.addEventListener("submit", saveMemory);
  void approvals;
}

function navigate(route) {
  const normalized = route === "current-context" ? "context" : route;
  view.route = normalized;
  view.error = "";
  window.location.hash = `/${normalized}`;
  render();
  void loadRouteData();
}

function openPalette() {
  view.paletteOpen = true;
  view.paletteQuery = "";
  render();
  document.querySelector("[data-palette-input]")?.focus();
}

async function submitMessage(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const input = form.elements.message;
  const value = input.value.trim();
  if (!value || view.sending) return;
  view.sending = true;
  view.error = "";
  render();
  try {
    const payload = { text: value, client_message_id: `ui-${crypto.randomUUID()}` };
    if (view.selectedConversation) payload.conversation_id = view.selectedConversation;
    const result = await request("/messages", { method: "POST", body: payload });
    view.selectedConversation = result.conversation_id;
    await Promise.all([refreshConversations(), loadMessages(), refreshState(false)]);
  } catch (error) {
    view.error = error instanceof Error ? error.message : "Message failed.";
  } finally {
    view.sending = false;
    render();
  }
}

async function decideApproval(button) {
  const approvalId = button.dataset.approval;
  const runId = button.dataset.run;
  if (!approvalId || !runId) return;
  button.disabled = true;
  try {
    await request(`/approvals/${encodeURIComponent(approvalId)}`, { method: "POST", body: { run_id: runId, approved: button.dataset.approved === "true" } });
    await refreshState(false);
  } catch (error) {
    view.error = error instanceof Error ? error.message : "Approval decision failed.";
  }
  render();
}

async function searchMemory(event) {
  event.preventDefault();
  const query = event.currentTarget.elements.query.value.trim();
  try {
    const payload = await request(ownerQuery("/memory", `&limit=50${query ? `&q=${encodeURIComponent(query)}` : ""}`));
    view.memory = array(payload.memories);
    view.error = "";
  } catch (error) {
    view.error = error instanceof Error ? error.message : "Memory search failed.";
  }
  render();
}

function editMemory(id) {
  const item = view.memory.find((candidate) => (candidate.memory_id || candidate.id) === id);
  if (item) {
    view.modal = { id, content: text(item.content, "") };
    render();
    document.querySelector("#memory-content")?.focus();
  }
}

async function saveMemory(event) {
  event.preventDefault();
  const content = event.currentTarget.elements.content.value.trim();
  if (!content || !view.modal) return;
  try {
    await request(`/memory/${encodeURIComponent(view.modal.id)}`, { method: "PATCH", body: { content } });
    view.modal = null;
    const payload = await request(ownerQuery("/memory", "&limit=50"));
    view.memory = array(payload.memories);
  } catch (error) {
    view.error = error instanceof Error ? error.message : "Memory update failed.";
  }
  render();
}

async function deleteMemory(id) {
  if (!window.confirm("Delete this memory through the canonical MemoryService?")) return;
  try {
    await request(`/memory/${encodeURIComponent(id)}`, { method: "DELETE", body: {} });
    view.memory = view.memory.filter((item) => (item.memory_id || item.id) !== id);
  } catch (error) {
    view.error = error instanceof Error ? error.message : "Memory deletion failed.";
  }
  render();
}

window.addEventListener("hashchange", () => {
  view.route = routeFromLocation();
  void loadRouteData();
});

window.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    openPalette();
  } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
    event.preventDefault();
    view.selectedConversation = null;
    navigate("chat");
  } else if (event.key === "Escape" && (view.paletteOpen || view.modal)) {
    view.paletteOpen = false;
    view.modal = null;
    render();
  }
});

async function boot() {
  try {
    await establishSession();
    await refreshState(false);
    view.loading = false;
    render();
    await loadRouteData();
    window.setInterval(async () => {
      try { await refreshState(true); } catch (error) { view.error = error instanceof Error ? error.message : "The local runtime is unavailable."; render(); }
    }, 2000);
  } catch (error) {
    view.loading = false;
    view.error = error instanceof Error ? error.message : "The local session could not be established.";
    render();
  }
}

void boot();
