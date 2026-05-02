/**
 * Cyberpunk Companion — Frontend Application
 *
 * Manages:
 *  - WebSocket connection to the Python backend
 *  - NPC sprite rendering and animation
 *  - Chat UI
 *  - Action/event handling (move, mood, state changes, etc.)
 */

"use strict";

// ==========================================================================
// Configuration
// ==========================================================================
const WS_URL = "ws://localhost:8765";
const RECONNECT_DELAY_MS = 3000;
const BUBBLE_DURATION_MS = 6000;

// NPC avatar emoji map — fallback if no custom sprite is loaded.
const AVATAR_EMOJI = {
  aria:    "🤖",
  nexus:   "🧠",
  echo:    "💠",
  default: "👾",
};

// ==========================================================================
// State
// ==========================================================================
const state = {
  ws: null,
  connected: false,
  agents: {},          // npc_id → agent data
  bubbleTimers: {},    // npc_id → setTimeout handle
};

// ==========================================================================
// DOM references
// ==========================================================================
const $ = (id) => document.getElementById(id);
const canvas          = $("canvas");
const chatLog         = $("chat-log");
const chatInput       = $("chat-input");
const sendBtn         = $("send-btn");
const chatToggle      = $("chat-toggle");
const chatPanel       = $("chat-panel");
const targetSelect    = $("target-select");
const connectionDot   = $("connection-dot");
const connectionLabel = $("connection-label");
const agentCountEl    = $("agent-count");
const notifications   = $("notifications");
const btnQuit         = $("btn-quit");

// ==========================================================================
// WebSocket
// ==========================================================================
function connect() {
  setConnectionStatus("connecting");
  const ws = new WebSocket(WS_URL);

  ws.addEventListener("open", () => {
    state.ws = ws;
    state.connected = true;
    setConnectionStatus("connected");
    appendSystemMsg("// CONNECTION ESTABLISHED");
  });

  ws.addEventListener("message", (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      handleServerMessage(msg);
    } catch (e) {
      console.error("WS parse error:", e);
    }
  });

  ws.addEventListener("close", () => {
    state.ws = null;
    state.connected = false;
    setConnectionStatus("disconnected");
    appendSystemMsg("// CONNECTION LOST — RECONNECTING…");
    setTimeout(connect, RECONNECT_DELAY_MS);
  });

  ws.addEventListener("error", (err) => {
    console.error("WS error:", err);
    ws.close();
  });
}

function send(type, data) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type, data }));
  }
}

// ==========================================================================
// Message router
// ==========================================================================
function handleServerMessage(msg) {
  const { type, data } = msg;
  switch (type) {
    case "system:status":
      syncAgents(data.agents || []);
      break;
    case "agent:spawned":
      upsertAgent(data);
      break;
    case "agent:removed":
      removeAgent(data.npc_id);
      break;
    case "npc:response":
      onNPCResponse(data);
      break;
    case "npc:state_changed":
      onNPCStateChanged(data);
      break;
    case "npc:action":
      onNPCAction(data);
      break;
    case "npc:mood_changed":
      onNPCMoodChanged(data);
      break;
    default:
      break;
  }
}

// ==========================================================================
// Agent management
// ==========================================================================
function syncAgents(agents) {
  const incoming = new Set(agents.map((a) => a.npc_id));
  // Remove stale agents.
  for (const id of Object.keys(state.agents)) {
    if (!incoming.has(id)) removeAgent(id);
  }
  // Upsert all.
  agents.forEach(upsertAgent);
  updateAgentCount();
}

function upsertAgent(data) {
  const { npc_id } = data;
  if (!state.agents[npc_id]) {
    state.agents[npc_id] = data;
    createNPCElement(data);
    addTargetOption(npc_id, data.name);
  } else {
    Object.assign(state.agents[npc_id], data);
    updateNPCElement(data);
  }
  updateAgentCount();
}

function removeAgent(npc_id) {
  delete state.agents[npc_id];
  const el = document.getElementById(`npc-${npc_id}`);
  if (el) el.remove();
  // Remove from target select.
  const opt = targetSelect.querySelector(`option[value="${npc_id}"]`);
  if (opt) opt.remove();
  updateAgentCount();
}

function updateAgentCount() {
  const n = Object.keys(state.agents).length;
  agentCountEl.textContent = `${n} AGENT${n !== 1 ? "S" : ""}`;
}

// ==========================================================================
// NPC DOM elements
// ==========================================================================
function createNPCElement(data) {
  const { npc_id, name, avatar, mood, position, state: npcState } = data;

  const npc = document.createElement("div");
  npc.id = `npc-${npc_id}`;
  npc.className = "npc";
  npc.dataset.mood = mood || "neutral";
  npc.title = name;

  const bubble = document.createElement("div");
  bubble.className = "speech-bubble";
  bubble.id = `bubble-${npc_id}`;

  const avatarEl = document.createElement("div");
  avatarEl.className = `npc-avatar ${npcState || "idle"}`;
  avatarEl.id = `avatar-${npc_id}`;
  avatarEl.textContent = AVATAR_EMOJI[avatar] || AVATAR_EMOJI.default;

  const nameEl = document.createElement("div");
  nameEl.className = "npc-name";
  nameEl.textContent = name;

  const badgeEl = document.createElement("div");
  badgeEl.className = "npc-state-badge";
  badgeEl.id = `badge-${npc_id}`;
  badgeEl.textContent = (npcState || "idle").toUpperCase();

  npc.appendChild(bubble);
  npc.appendChild(avatarEl);
  npc.appendChild(nameEl);
  npc.appendChild(badgeEl);

  // Click on NPC → focus chat to that NPC.
  npc.addEventListener("click", () => {
    targetSelect.value = npc_id;
    chatInput.focus();
    chatPanel.classList.remove("collapsed");
  });

  canvas.appendChild(npc);
  positionNPC(npc_id, position);
}

function updateNPCElement(data) {
  const { npc_id, mood, position, state: npcState } = data;
  if (mood) {
    const npc = document.getElementById(`npc-${npc_id}`);
    if (npc) npc.dataset.mood = mood;
  }
  if (position) positionNPC(npc_id, position);
  if (npcState) updateStateBadge(npc_id, npcState);
}

function positionNPC(npc_id, position) {
  const npc = document.getElementById(`npc-${npc_id}`);
  if (!npc || !position) return;
  npc.style.left = `${position.x}%`;
  npc.style.top  = `${position.y}%`;
}

function updateStateBadge(npc_id, npcState) {
  const badge  = $(`badge-${npc_id}`);
  const avatar = $(`avatar-${npc_id}`);
  if (badge)  badge.textContent = npcState.toUpperCase();
  if (avatar) {
    avatar.className = "npc-avatar";
    if (!["idle", "listening"].includes(npcState)) {
      avatar.classList.add(npcState);
    }
  }
}

function showSpeechBubble(npc_id, text) {
  const bubble = $(`bubble-${npc_id}`);
  if (!bubble) return;

  bubble.textContent = text;
  bubble.classList.add("visible");

  // Clear any existing timer.
  clearTimeout(state.bubbleTimers[npc_id]);
  state.bubbleTimers[npc_id] = setTimeout(() => {
    bubble.classList.remove("visible");
  }, BUBBLE_DURATION_MS);
}

// ==========================================================================
// Event handlers (from server)
// ==========================================================================
function onNPCResponse(data) {
  const { npc_id, name, text, mood, position, state: npcState } = data;

  if (text) {
    showSpeechBubble(npc_id, text);
    appendChatMsg("npc", name, text);
  }
  if (mood) {
    const npc = document.getElementById(`npc-${npc_id}`);
    if (npc) npc.dataset.mood = mood;
  }
  if (position) positionNPC(npc_id, position);
  updateStateBadge(npc_id, npcState || "idle");
}

function onNPCStateChanged(data) {
  const { npc_id, state: npcState } = data;
  updateStateBadge(npc_id, npcState);
}

function onNPCAction(data) {
  const { npc_id, action, args } = data;
  const agent = state.agents[npc_id];
  const name  = agent ? agent.name : npc_id;

  // Handle positional moves.
  if (action === "move_to" && args) {
    positionNPC(npc_id, { x: args.x, y: args.y });
  }

  // Show notification for interesting actions.
  if (["move_to", "play_animation", "execute_narrative_task"].includes(action)) {
    showNotification(
      `[${name}] ${action.toUpperCase().replace(/_/g, " ")}`,
      "action"
    );
  }
}

function onNPCMoodChanged(data) {
  const { npc_id, mood } = data;
  const npc = document.getElementById(`npc-${npc_id}`);
  if (npc) npc.dataset.mood = mood;
  if (state.agents[npc_id]) state.agents[npc_id].mood = mood;
}

// ==========================================================================
// Chat
// ==========================================================================
function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  const target = targetSelect.value || null;
  appendChatMsg("user", "YOU", text);
  send("user:message", {
    text,
    sender: "user",
    target_npc_id: target || undefined,
  });
  chatInput.value = "";
}

function appendChatMsg(role, sender, text) {
  const msg = document.createElement("div");
  msg.className = `chat-msg ${role}`;

  const senderEl = document.createElement("div");
  senderEl.className = "chat-msg-sender";
  senderEl.textContent = sender.toUpperCase();

  const textEl = document.createElement("div");
  textEl.textContent = text;

  msg.appendChild(senderEl);
  msg.appendChild(textEl);
  chatLog.appendChild(msg);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function appendSystemMsg(text) {
  const msg = document.createElement("div");
  msg.className = "chat-msg system";
  msg.textContent = text;
  chatLog.appendChild(msg);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function addTargetOption(value, label) {
  if (targetSelect.querySelector(`option[value="${value}"]`)) return;
  const opt = document.createElement("option");
  opt.value = value;
  opt.textContent = label;
  targetSelect.appendChild(opt);
}

// ==========================================================================
// Notifications
// ==========================================================================
function showNotification(text, type = "") {
  const el = document.createElement("div");
  el.className = `notif ${type}`;
  el.textContent = text;
  notifications.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ==========================================================================
// Connection status
// ==========================================================================
function setConnectionStatus(status) {
  connectionDot.className = `dot ${status}`;
  connectionLabel.textContent = {
    connected:    "CONNECTED",
    disconnected: "DISCONNECTED",
    connecting:   "CONNECTING…",
  }[status] || status.toUpperCase();
}

// ==========================================================================
// Event listeners
// ==========================================================================
sendBtn.addEventListener("click", sendMessage);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage();
});

chatToggle.addEventListener("click", () => {
  chatPanel.classList.toggle("collapsed");
});

btnQuit.addEventListener("click", () => {
  if (window.electronAPI) window.electronAPI.quit();
  else window.close();
});

// ==========================================================================
// Boot
// ==========================================================================
connect();
appendSystemMsg("// COMPANION OS v1.0 INITIALISING…");
