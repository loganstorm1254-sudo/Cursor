import { createVoiceSession } from "/voice.js";

const auth = document.querySelector("#auth");
const authForm = document.querySelector("#auth-form");
const authTitle = document.querySelector("#auth-title");
const authLede = document.querySelector("#auth-lede");
const authError = document.querySelector("#auth-error");
const authSubmit = document.querySelector("#auth-submit");
const authSwitch = document.querySelector("#auth-switch");
const authTabLogin = document.querySelector("#auth-tab-login");
const authTabRegister = document.querySelector("#auth-tab-register");
const usernameInput = document.querySelector("#username");
const passwordInput = document.querySelector("#password");
const boot = document.querySelector("#boot");
const shell = document.querySelector("#shell");
const rail = document.querySelector("#rail");
const channelsEl = document.querySelector("#channels");
const topbar = document.querySelector("#topbar");
const transcript = document.querySelector("#transcript");
const composer = document.querySelector("#composer");
const messageInput = document.querySelector("#message");
const membersEl = document.querySelector("#members");
const backdrop = document.querySelector("#drawer-backdrop");
const modal = document.querySelector("#modal");
const modalForm = document.querySelector("#modal-form");
const emojiButton = document.querySelector("#emoji-button");
const emojiPanel = document.querySelector("#emoji-panel");

const PUBLIC_ORIGIN = "https://hallchat.lopro.cc";
const POLL_PREFIX = "§HALLPOLL§";
const INVITE_PENDING_KEY = "hall.pendingInvite";
const EMOJI_SHORTCODES = {
  smile: "😄",
  grin: "😁",
  joy: "😂",
  wink: "😉",
  heart: "❤️",
  hearts: "💕",
  fire: "🔥",
  thumbsup: "👍",
  thumbsdown: "👎",
  clap: "👏",
  wave: "👋",
  think: "🤔",
  cry: "😢",
  sob: "😭",
  angry: "😠",
  cool: "😎",
  party: "🥳",
  tada: "🎉",
  100: "💯",
  check: "✅",
  cross: "❌",
  star: "⭐",
  eyes: "👀",
  skull: "💀",
  rocket: "🚀",
  coffee: "☕",
  pizza: "🍕",
  moon: "🌙",
  sun: "☀️",
  ok: "👌",
  pray: "🙏",
  muscle: "💪",
  sparkles: "✨",
};
const EMOJI_PICKER = Object.values(EMOJI_SHORTCODES);

const state = {
  mode: "register",
  me: null,
  servers: [],
  server: null,
  channels: [],
  members: [],
  messages: [],
  hasMore: false,
  online: new Map(),
  activeServerId: null,
  activeChannelId: null,
  socket: null,
  socketAbort: null,
  pingTimer: null,
  voice: { active: false, muted: false, channelId: null, peers: [] },
  home: false,
  friends: [],
  incoming: [],
  outgoing: [],
  dms: [],
  dmPeer: null,
  hubSocket: null,
  hubAbort: null,
  hubPing: null,
};

let socketGeneration = 0;
let hubGeneration = 0;
const voiceSession = createVoiceSession({
  getSocket: () => state.socket,
  getMe: () => state.me,
  onState: (next) => {
    state.voice = next;
    renderVoiceStage();
    renderTopbar();
    renderMembers();
    if (state.home) renderHomeSidebar();
  },
});

function hue(name) {
  let hash = 0;
  for (const char of name) hash = (hash * 33 + char.charCodeAt(0)) >>> 0;
  return hash % 360;
}

function avatarNode(person, sizeClass = "avatar") {
  const name = person.displayName || person.username || "?";
  const node = el("button", {
    class: sizeClass,
    type: "button",
    title: `@${person.username || name}`,
    style: person.avatarUrl ? "" : `background: hsl(${hue(person.username || name)} 62% 62%)`,
    onclick: (event) => {
      event.stopPropagation();
      if (person.username) openProfile(person.username, person.id === state.me?.id);
    },
  });
  if (person.avatarUrl) {
    node.append(el("img", { src: person.avatarUrl, alt: "", decoding: "async" }));
  } else {
    node.append(text(name.slice(0, 1).toUpperCase()));
  }
  return node;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "style" && typeof value === "string") node.style.cssText = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value !== undefined && value !== null && value !== false) node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children) {
    if (child !== null && child !== undefined && child !== false) node.append(child);
  }
  return node;
}

function text(value) {
  return document.createTextNode(value);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || "Request failed");
    error.status = response.status;
    throw error;
  }
  return data;
}

function showAuth() {
  boot.hidden = true;
  boot.removeAttribute("aria-busy");
  shell.hidden = true;
  auth.hidden = false;
  closeSocket();
}

function showApp() {
  boot.hidden = true;
  boot.removeAttribute("aria-busy");
  auth.hidden = true;
  shell.hidden = false;
}

function setAuthMode(mode) {
  state.mode = mode;
  const register = mode === "register";
  authTitle.textContent = register ? "Create your account" : "Welcome back";
  authLede.textContent = register
    ? "Pick a username. If nobody has it, it is yours."
    : "Sign in with the username you claimed.";
  authSubmit.textContent = register ? "Create account" : "Sign in";
  authSwitch.textContent = register ? "Already have an account? Sign in" : "Need an account? Create one";
  passwordInput.autocomplete = register ? "new-password" : "current-password";
  authError.textContent = "";
  if (authTabLogin && authTabRegister) {
    authTabLogin.setAttribute("aria-selected", register ? "false" : "true");
    authTabRegister.setAttribute("aria-selected", register ? "true" : "false");
    authTabLogin.classList.toggle("active", !register);
    authTabRegister.classList.toggle("active", register);
  }
}

authSwitch.addEventListener("click", () => setAuthMode(state.mode === "register" ? "login" : "register"));
authTabLogin?.addEventListener("click", () => setAuthMode("login"));
authTabRegister?.addEventListener("click", () => setAuthMode("register"));

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authError.textContent = "";
  authSubmit.disabled = true;
  try {
    const data = await api(state.mode === "register" ? "/api/register" : "/api/login", {
      method: "POST",
      body: JSON.stringify({ username: usernameInput.value, password: passwordInput.value }),
    });
    state.me = data.user;
    passwordInput.value = "";
    await enterApp();
  } catch (error) {
    authError.textContent = error.message;
  } finally {
    authSubmit.disabled = false;
  }
});

function inviteLink(code) {
  return `${PUBLIC_ORIGIN}/invite/${encodeURIComponent(String(code || "").trim().toLowerCase())}`;
}

function extractInviteCode(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(raw, PUBLIC_ORIGIN);
    const pathMatch = url.pathname.match(/^\/invite\/([a-z0-9-]{2,32})\/?$/i);
    if (pathMatch?.[1]) return pathMatch[1].toLowerCase();
    const queryCode = url.searchParams.get("invite");
    if (queryCode && /^[a-z0-9-]{2,32}$/i.test(queryCode)) return queryCode.toLowerCase();
  } catch {
    // Fall through to bare codes.
  }
  const bare = raw.replace(/^@/, "").toLowerCase();
  if (/^[a-z0-9-]{2,32}$/.test(bare)) return bare;
  return "";
}

function pendingInviteCode() {
  return sessionStorage.getItem(INVITE_PENDING_KEY) || extractInviteCode(location.href) || "";
}

function captureInviteFromLocation() {
  const code = extractInviteCode(location.href);
  if (!code) return;
  sessionStorage.setItem(INVITE_PENDING_KEY, code);
  // Keep a stable in-scope URL so the installed Hall app can claim the link.
  if (location.pathname.startsWith("/invite/")) {
    history.replaceState({}, "", `/?invite=${encodeURIComponent(code)}`);
  }
}

async function consumePendingInvite() {
  const code = pendingInviteCode();
  if (!code) return null;
  try {
    const data = await api("/api/join", { method: "POST", body: JSON.stringify({ code }) });
    sessionStorage.removeItem(INVITE_PENDING_KEY);
    if (location.search.includes("invite=")) history.replaceState({}, "", "/");
    return data.server?.id ?? null;
  } catch (error) {
    openModal("Invite", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message || "Could not use that invite.")]));
    });
    return null;
  }
}

async function enterApp() {
  showApp();
  if (boot.querySelector("p")) boot.querySelector("p").textContent = pendingInviteCode() ? "Joining server…" : "Hall";
  const invitedServerId = await consumePendingInvite();
  const listed = await api("/api/servers");
  state.servers = listed.servers;
  renderRail();
  const preferred =
    state.servers.find((server) => server.id === invitedServerId) ??
    state.servers.find((server) => server.id === state.activeServerId) ??
    state.servers[0];
  if (!preferred) {
    state.server = null;
    state.channels = [];
    state.members = [];
    state.messages = [];
    state.activeServerId = null;
    state.activeChannelId = null;
    renderChannels();
    renderMessages(false);
    renderMembers();
    renderTopbar();
    return;
  }
  await openServer(preferred.id);
}

async function moveServer(serverId, direction) {
  const index = state.servers.findIndex((server) => server.id === serverId);
  if (index < 0) return;
  const swap = index + direction;
  if (swap < 0 || swap >= state.servers.length) return;
  const next = [...state.servers];
  const [item] = next.splice(index, 1);
  next.splice(swap, 0, item);
  state.servers = next;
  renderRail();
  try {
    await api("/api/servers/order", {
      method: "PUT",
      body: JSON.stringify({ serverIds: next.map((server) => server.id) }),
    });
  } catch (error) {
    openModal("Could not reorder", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message)]));
    });
    const listed = await api("/api/servers");
    state.servers = listed.servers;
    renderRail();
  }
}

function connectHub(serverId) {
  const generation = ++hubGeneration;
  closeHub(false);
  if (!serverId || serverId === "home") return;
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/api/servers/${encodeURIComponent(serverId)}/websocket`);
  const abort = new AbortController();
  state.hubSocket = socket;
  state.hubAbort = abort;
  state.hubPing = setInterval(() => {
    if (socket.readyState === WebSocket.OPEN) socket.send("ping");
  }, 25000);
  socket.addEventListener("message", (event) => {
    if (generation !== hubGeneration || typeof event.data !== "string" || event.data === "pong") return;
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }
    if (payload.type === "channels" && Array.isArray(payload.channels) && state.activeServerId === serverId) {
      const active = state.activeChannelId;
      state.channels = payload.channels;
      renderChannels();
      if (active && !state.channels.some((channel) => channel.id === active)) {
        const fallback = state.channels.find((channel) => (channel.kind || "text") !== "voice") || state.channels[0];
        if (fallback) openChannel(fallback.id);
      } else {
        renderTopbar();
      }
    }
  }, { signal: abort.signal });
  socket.addEventListener("close", () => {
    if (state.hubPing) {
      clearInterval(state.hubPing);
      state.hubPing = null;
    }
    if (generation !== hubGeneration) return;
    setTimeout(() => {
      if (generation === hubGeneration && state.activeServerId === serverId && !state.home) connectHub(serverId);
    }, 1200);
  }, { signal: abort.signal });
}

function closeHub(bump = true) {
  if (bump) hubGeneration += 1;
  if (state.hubPing) {
    clearInterval(state.hubPing);
    state.hubPing = null;
  }
  if (state.hubAbort) {
    state.hubAbort.abort();
    state.hubAbort = null;
  }
  const socket = state.hubSocket;
  state.hubSocket = null;
  if (!socket) return;
  try {
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) socket.close(1000, "switch");
  } catch {
    // ignore
  }
}

function renderRail() {
  rail.replaceChildren();
  rail.append(el("button", {
    class: state.home ? "server-button home-button" : "server-button home-button dim",
    type: "button",
    title: "Home · Friends & DMs",
    "aria-current": state.home ? "true" : null,
    onclick: () => openHome(),
  }, [text("⌂")]));
  state.servers.forEach((server, index) => {
    const icon = server.avatarUrl
      ? el("img", { src: server.avatarUrl, alt: "", class: "server-icon" })
      : text(server.iconLetter);
    const button = el("button", {
      class: "server-button",
      type: "button",
      title: server.name,
      "aria-current": !state.home && server.id === state.activeServerId ? "true" : null,
      onclick: async () => {
        await openServer(server.id);
        closeDrawers();
        openDrawer("channels");
      },
    }, [icon]);
    const wrap = el("div", { class: "server-slot" }, [
      button,
      el("div", { class: "server-move" }, [
        el("button", {
          class: "ghost server-move-btn",
          type: "button",
          "aria-label": "Move server up",
          disabled: index === 0 ? "disabled" : null,
          onclick: (event) => {
            event.stopPropagation();
            moveServer(server.id, -1);
          },
        }, [text("↑")]),
        el("button", {
          class: "ghost server-move-btn",
          type: "button",
          "aria-label": "Move server down",
          disabled: index === state.servers.length - 1 ? "disabled" : null,
          onclick: (event) => {
            event.stopPropagation();
            moveServer(server.id, 1);
          },
        }, [text("↓")]),
      ]),
    ]);
    rail.append(wrap);
  });
  rail.append(el("button", {
    class: "add-server",
    type: "button",
    title: "Add a server",
    "aria-label": "Add a server",
    onclick: () => {
      closeDrawers();
      openAddMenu();
    },
  }, [text("+")]));
}

function closeDrawers() {
  channelsEl.classList.remove("open");
  membersEl.classList.remove("open");
  rail.classList.remove("open");
  if (backdrop) {
    backdrop.classList.remove("show");
    backdrop.hidden = true;
  }
}

function openDrawer(which) {
  closeDrawers();
  if (which === "channels") channelsEl.classList.add("open");
  if (which === "members") membersEl.classList.add("open");
  if (which === "servers") rail.classList.add("open");
  if (backdrop && which) {
    backdrop.hidden = false;
    backdrop.classList.add("show");
  }
}

function canManageActiveServer() {
  const server = state.server;
  if (!server) return false;
  if (server.canManage != null) return Boolean(server.canManage);
  return server.isLobby ? Boolean(state.me?.isPlatformOwner) : Boolean(server.isOwner);
}

async function deleteChannel(channelId, channelName) {
  if (!canManageActiveServer()) return;
  if (state.channels.length <= 1) {
    openModal("Keep a channel", (form) => {
      form.append(el("p", {}, [text("Servers need at least one channel.")]));
    });
    return;
  }
  openModal(`Delete #${channelName}?`, (form) => {
    const error = el("p", { class: "form-error", role: "alert" });
    form.append(
      el("p", { class: "lede" }, [text("Messages in this channel will no longer be reachable from Hall.")]),
      error,
      el("div", { class: "actions" }, [
        el("button", { class: "ghost", type: "button", onclick: () => modal.close() }, [text("Cancel")]),
        el("button", {
          type: "submit",
          style: "background: var(--danger); color: #1a0d0a;",
        }, [text("Delete")]),
      ]),
    );
    form.onsubmit = async (event) => {
      event.preventDefault();
      error.textContent = "";
      try {
        await api(`/api/channels/${encodeURIComponent(channelId)}`, { method: "DELETE" });
        modal.close();
        const wasActive = state.activeChannelId === channelId;
        state.channels = state.channels.filter((channel) => channel.id !== channelId);
        if (wasActive) {
          const next = state.channels[0];
          if (next) await openChannel(next.id);
          else {
            state.activeChannelId = null;
            state.messages = [];
            closeSocket();
            renderTopbar();
            renderMessages(true);
          }
        }
        renderChannels();
      } catch (err) {
        error.textContent = err.message;
      }
    };
  });
}

async function moveChannel(channelId, direction) {
  const index = state.channels.findIndex((channel) => channel.id === channelId);
  if (index < 0) return;
  const swap = index + direction;
  if (swap < 0 || swap >= state.channels.length) return;
  const next = [...state.channels];
  const [item] = next.splice(index, 1);
  next.splice(swap, 0, item);
  state.channels = next;
  renderChannels();
  try {
    await api(`/api/servers/${encodeURIComponent(state.server.id)}/channel-order`, {
      method: "PUT",
      body: JSON.stringify({ channelIds: next.map((channel) => channel.id) }),
    });
  } catch (error) {
    openModal("Could not reorder", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message)]));
    });
    if (state.activeServerId) await openServer(state.activeServerId);
  }
}

function renderChannels() {
  const server = state.server;
  if (!server) {
    channelsEl.replaceChildren(el("div", { class: "empty" }, [text("Create or join a server to start talking.")]));
    return;
  }
  const manage = canManageActiveServer();
  const list = el("ul", { class: "channel-list" });
  const textChannels = state.channels.filter((channel) => (channel.kind || "text") !== "voice");
  const voiceChannels = state.channels.filter((channel) => channel.kind === "voice");
  const sections = [
    { label: "Text", items: textChannels },
    { label: "Voice", items: voiceChannels },
  ];
  for (const section of sections) {
    if (section.items.length === 0 && section.label === "Voice" && !manage) continue;
    list.append(el("li", { class: "channel-section" }, [text(section.label)]));
    if (section.items.length === 0) {
      list.append(el("li", { class: "channel-empty" }, [text(section.label === "Voice" ? "No VCs yet" : "No channels")]));
    }
    section.items.forEach((channel) => {
      const index = state.channels.findIndex((item) => item.id === channel.id);
      const isVoice = channel.kind === "voice";
      const row = [
        el("button", {
          type: "button",
          class: "channel-open",
          "aria-current": channel.id === state.activeChannelId ? "true" : null,
          onclick: () => openChannel(channel.id),
        }, [
          el("span", { class: isVoice ? "hash voice-hash" : "hash" }, [text(isVoice ? "🔊" : "#")]),
          text(channel.name),
        ]),
      ];
      if (manage) {
        row.push(el("div", { class: "channel-move" }, [
          el("button", {
            class: "ghost channel-move-btn",
            type: "button",
            "aria-label": "Move up",
            disabled: index <= 0 ? "disabled" : null,
            onclick: () => moveChannel(channel.id, -1),
          }, [text("↑")]),
          el("button", {
            class: "ghost channel-move-btn",
            type: "button",
            "aria-label": "Move down",
            disabled: index < 0 || index >= state.channels.length - 1 ? "disabled" : null,
            onclick: () => moveChannel(channel.id, 1),
          }, [text("↓")]),
          el("button", {
            class: "ghost channel-move-btn channel-delete-btn",
            type: "button",
            "aria-label": `Delete ${isVoice ? "VC" : "#"}${channel.name}`,
            disabled: !isVoice && textChannels.length <= 1 ? "disabled" : null,
            onclick: () => deleteChannel(channel.id, channel.name),
          }, [text("×")]),
        ]));
      }
      list.append(el("li", { class: manage ? "channel-row manage" : "channel-row" }, row));
    });
  }
  const foot = el("div", { class: "side-foot" });
  const link = inviteLink(server.inviteCode);
  const invite = el("div", { class: "invite" }, [
    el("div", { class: "invite-label" }, [text("Invite link")]),
    el("code", { class: "invite-link" }, [text(link)]),
  ]);
  invite.append(el("button", { class: "ghost", type: "button", onclick: copyInvite }, [text("Copy link")]));
  foot.append(invite);
  if (manage) {
    foot.append(el("button", { class: "ghost", type: "button", onclick: () => openCreateChannel("text") }, [text("Add text channel")]));
    foot.append(el("button", { class: "ghost", type: "button", onclick: () => openCreateChannel("voice") }, [text("Create VC")]));
  }
  if (!server.isLobby && !server.isOwner && !server.unleavable) {
    foot.append(el("button", { class: "text-button", type: "button", onclick: leaveServer }, [text("Leave server")]));
  }
  const me = el("div", { class: "me-row" }, [
    avatarNode(state.me, "avatar sm"),
    el("div", { class: "me-meta" }, [
      el("strong", {}, [text(state.me.displayName)]),
      el("span", {}, [text(`@${state.me.username}`)]),
    ]),
    el("div", { class: "me-actions" }, [
      el("button", { class: "text-button", type: "button", onclick: () => openProfile(state.me.username, true) }, [text("Profile")]),
      el("button", { class: "text-button", type: "button", onclick: logout }, [text("Log out")]),
    ]),
  ]);
  foot.append(me);
  const headActions = [];
  if (canManageActiveServer()) {
    headActions.push(el("button", {
      class: "ghost",
      type: "button",
      onclick: openServerSettings,
    }, [text("Edit")]));
  }
  headActions.push(el("button", {
    class: "ghost drawer-close",
    type: "button",
    "aria-label": "Close",
    onclick: closeDrawers,
  }, [text("Close")]));
  channelsEl.replaceChildren(
    el("div", { class: "side-head" }, [
      el("div", { class: "side-head-title" }, [
        el("h2", {}, [text(server.name)]),
        server.bio ? el("p", { class: "server-bio" }, [text(server.bio)]) : null,
      ]),
      el("div", { class: "side-head-actions" }, headActions),
    ]),
    list,
    foot,
  );
  renderVoiceStage();
}

function renderTopbar() {
  const channel = state.channels.find((item) => item.id === state.activeChannelId);
  const isVoice = channel?.kind === "voice";
  const isDm = state.home && state.activeChannelId?.startsWith("dm:");
  const title = isDm
    ? `@${state.dmPeer?.username || "dm"}`
    : channel
      ? `${isVoice ? "🔊" : "#"}${channel.name}`
      : state.home
        ? "Home"
        : "Hall";
  messageInput.placeholder = isDm
    ? `Message @${state.dmPeer?.username || "friend"}`
    : channel && !isVoice
      ? `Message #${channel.name}`
      : "Message";
  const inThisVoice = state.voice.active && state.voice.channelId === state.activeChannelId;
  const voiceCount = state.voice.peers?.length || 0;
  topbar.replaceChildren(
    el("div", { class: "topbar-actions" }, [
      el("button", {
        class: "ghost servers-button",
        type: "button",
        "aria-label": "Servers",
        onclick: () => openDrawer("servers"),
      }, [text("Srv")]),
      el("button", {
        class: "ghost menu-button",
        type: "button",
        "aria-label": state.home ? "Friends" : "Channels",
        onclick: () => openDrawer("channels"),
      }, [text(state.home ? "Home" : "#")]),
    ]),
    el("div", { class: "topbar-title" }, [
      el("h2", {}, [text(title)]),
      el("p", {}, [text(isDm ? "Direct message" : state.home ? "Friends & DMs" : state.server ? state.server.name : "No server")]),
    ]),
    el("div", { class: "topbar-actions topbar-end" }, [
      state.activeChannelId && (isVoice || isDm)
        ? el("button", {
            class: inThisVoice ? "ghost voice-button on" : "ghost voice-button",
            type: "button",
            "aria-label": inThisVoice ? "Leave call" : isDm ? "Start call" : "Join voice",
            onclick: () => toggleVoice(),
          }, [text(inThisVoice ? `In call · ${voiceCount}` : isDm ? "Call" : "Voice")])
        : null,
      state.home
        ? null
        : el("button", {
            class: "ghost people-button",
            type: "button",
            "aria-label": "Members",
            onclick: () => openDrawer("members"),
          }, [text("People")]),
    ]),
  );
}

function renderVoiceStage() {
  const stage = document.querySelector("#voice-stage");
  if (!stage) return;
  const active = state.channels.find((item) => item.id === state.activeChannelId);
  const voiceChannel = state.channels.find((item) => item.id === state.voice.channelId);
  const isDmCall = Boolean(state.voice.channelId?.startsWith("dm:") || (state.home && state.activeChannelId?.startsWith("dm:") && state.voice.active));
  const channel = voiceChannel
    || active
    || (isDmCall || (state.home && state.voice.active) ? { name: state.dmPeer?.displayName || "DM", kind: "voice" } : null);
  const showStage = state.voice.active || active?.kind === "voice";
  if (!showStage) {
    stage.hidden = true;
    stage.replaceChildren();
    document.querySelector("#voice-dock")?.remove();
    return;
  }
  stage.hidden = false;
  const peers = state.voice.active ? state.voice.peers || [] : [];
  const tiles = peers.length
    ? peers.map((peer) => {
        const mine = peer.userId === state.me?.id;
        return el("div", { class: mine ? "voice-tile me" : "voice-tile" }, [
          avatarNode({ ...peer, id: peer.userId }, "avatar lg"),
          el("strong", {}, [text(peer.displayName)]),
          el("span", { class: "voice-tile-status" }, [text(peer.muted ? "Muted" : mine ? "You" : "In call")]),
        ]);
      })
    : [
        el("div", { class: "voice-tile empty-tile" }, [
          el("strong", {}, [text(channel?.name || "Voice")]),
          el("span", { class: "voice-tile-status" }, [text("Nobody here yet — join to talk")]),
        ]),
      ];
  stage.replaceChildren(
    el("div", { class: "voice-stage-grid" }, tiles),
    el("div", { class: "voice-controls" }, [
      el("button", {
        class: state.voice.muted ? "voice-ctrl mute on" : "voice-ctrl mute",
        type: "button",
        title: state.voice.muted ? "Unmute" : "Mute",
        disabled: !state.voice.active ? "disabled" : null,
        onclick: () => voiceSession.toggleMute(),
      }, [text(state.voice.muted ? "Unmute" : "Mute")]),
      el("button", {
        class: "voice-ctrl join",
        type: "button",
        onclick: () => toggleVoice(),
      }, [text(state.voice.active ? "Connected" : "Join")]),
      el("button", {
        class: "voice-ctrl hangup",
        type: "button",
        title: "Disconnect",
        disabled: !state.voice.active ? "disabled" : null,
        onclick: () => voiceSession.leave(),
      }, [text("Leave")]),
    ]),
  );

  let dock = document.querySelector("#voice-dock");
  if (state.voice.active) {
    if (!dock) {
      dock = el("div", { id: "voice-dock", class: "voice-dock" });
      document.querySelector("#channels")?.append(dock);
    }
    const label = state.voice.channelId?.startsWith("dm:")
      ? `Call · ${state.dmPeer?.displayName || "DM"}`
      : `Voice · ${channel?.name || "channel"}`;
    dock.replaceChildren(
      el("div", { class: "voice-dock-meta" }, [
        el("strong", {}, [text("Voice Connected")]),
        el("span", {}, [text(label)]),
      ]),
      el("div", { class: "voice-dock-actions" }, [
        el("button", {
          class: "ghost",
          type: "button",
          onclick: () => voiceSession.toggleMute(),
        }, [text(state.voice.muted ? "Unmute" : "Mute")]),
        el("button", {
          class: "ghost hangup-mini",
          type: "button",
          onclick: () => voiceSession.leave(),
        }, [text("Hang up")]),
      ]),
    );
  } else {
    dock?.remove();
  }
}

async function toggleVoice() {
  if (!state.activeChannelId) return;
  if (state.voice.active && state.voice.channelId === state.activeChannelId) {
    await voiceSession.leave();
    return;
  }
  try {
    await voiceSession.join(state.activeChannelId);
  } catch (error) {
    openModal("Voice", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message || "Could not start voice")]));
    });
  }
}

function renderMessages(stick) {
  const wasNearBottom = stick || nearBottom(transcript);
  const nodes = [];
  if (state.hasMore) {
    nodes.push(el("button", { class: "ghost load-older", type: "button", onclick: loadOlder }, [text("Load older")]));
  }
  if (state.messages.length === 0) {
    nodes.push(el("div", { class: "empty" }, [text("This channel is quiet. Say something.")]));
  }
  let previous = null;
  for (const message of state.messages) {
    const grouped = previous && previous.userId === message.userId && message.createdAt - previous.createdAt < 5 * 60 * 1000;
    const avatar = avatarNode(message);
    const header = el("header", {}, [
      el("button", {
        class: "author linkish",
        type: "button",
        onclick: () => openProfile(message.username, message.userId === state.me?.id),
      }, [text(message.displayName)]),
      el("span", { class: "handle" }, [text(`@${message.username}`)]),
      el("time", { class: "time", datetime: new Date(message.createdAt).toISOString() }, [text(formatTime(message.createdAt))]),
    ]);
    const poll = parsePollBody(message.body);
    const body = poll
      ? renderPoll(message, poll)
      : (() => {
          const node = el("p", { class: "body" });
          appendRichText(node, message.body);
          return node;
        })();
    const column = el("div", {}, grouped && !poll ? [body] : [header, body]);
    nodes.push(el("article", {
      class: `${grouped && !poll ? "message grouped" : "message"}${poll ? " has-poll" : ""}`,
      "data-message-id": message.id,
    }, [avatar, column]));
    previous = message;
  }
  transcript.replaceChildren(...nodes);
  if (wasNearBottom) transcript.scrollTop = transcript.scrollHeight;
}

function renderMembers() {
  const onlineCount = state.members.filter((member) => state.online.has(member.id)).length;
  const list = el("ul", { class: "member-list" });
  const ordered = [...state.members].sort((a, b) => {
    const ao = state.online.has(a.id) ? 0 : 1;
    const bo = state.online.has(b.id) ? 0 : 1;
    if (ao !== bo) return ao - bo;
    return a.displayName.localeCompare(b.displayName);
  });
  const inVoice = new Map((state.voice.peers || []).map((peer) => [peer.userId, peer]));
  for (const member of ordered) {
    const online = state.online.has(member.id);
    const voice = inVoice.get(member.id);
    const roleLabel = member.isPlatformOwner ? "hall owner" : member.isOwner ? "owner" : null;
    list.append(el("li", {
      class: "member-item",
      onclick: () => openProfile(member.username, member.id === state.me?.id),
    }, [
      el("span", { class: online ? "dot on" : "dot" }),
      avatarNode(member, "avatar tiny"),
      el("span", { class: "member-name" }, [text(member.displayName)]),
      voice ? el("span", { class: "role voice-tag" }, [text(voice.muted ? "muted" : "voice")]) : null,
      roleLabel ? el("span", { class: "role" }, [text(roleLabel)]) : null,
    ]));
  }
  membersEl.replaceChildren(
    el("div", { class: "side-head" }, [
      el("h2", {}, [text(`Online — ${onlineCount}`)]),
      el("button", {
        class: "ghost drawer-close",
        type: "button",
        "aria-label": "Close",
        onclick: closeDrawers,
      }, [text("Close")]),
    ]),
    list,
  );
}

function expandEmojiShortcodes(value) {
  return value.replace(/:([a-z0-9_]+):/gi, (full, name) => EMOJI_SHORTCODES[name.toLowerCase()] || full);
}

function appendRichText(node, value) {
  const expanded = expandEmojiShortcodes(value);
  const pattern = /https?:\/\/[^\s<]+/g;
  let last = 0;
  for (const match of expanded.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > last) node.append(text(expanded.slice(last, index)));
    const href = match[0];
    node.append(el("a", { href, target: "_blank", rel: "noreferrer noopener" }, [text(href)]));
    last = index + href.length;
  }
  if (last < expanded.length) node.append(text(expanded.slice(last)));
}

function parsePollBody(body) {
  if (!body?.startsWith(POLL_PREFIX)) return null;
  try {
    const poll = JSON.parse(body.slice(POLL_PREFIX.length));
    if (!poll?.question || !Array.isArray(poll.options)) return null;
    return poll;
  } catch {
    return null;
  }
}

function renderPoll(message, poll) {
  const votes = poll.votes || {};
  const total = Object.values(votes).reduce((sum, list) => sum + (list?.length || 0), 0);
  const myId = state.me?.id;
  const options = poll.options.map((label, index) => {
    const voters = votes[String(index)] || [];
    const count = voters.length;
    const pct = total ? Math.round((count / total) * 100) : 0;
    const mine = myId && voters.includes(myId);
    return el("button", {
      class: mine ? "poll-option mine" : "poll-option",
      type: "button",
      onclick: () => voteOnPoll(message.id, index),
    }, [
      el("span", { class: "poll-label" }, [text(expandEmojiShortcodes(label))]),
      el("span", { class: "poll-meta" }, [text(`${count} · ${pct}%`)]),
      el("span", { class: "poll-bar", style: `width:${pct}%` }),
    ]);
  });
  return el("div", { class: "poll" }, [
    el("p", { class: "poll-q" }, [text(expandEmojiShortcodes(poll.question))]),
    ...options,
    el("p", { class: "poll-total" }, [text(`${total} vote${total === 1 ? "" : "s"} · tap to vote`)]),
  ]);
}

async function voteOnPoll(messageId, optionIndex) {
  if (!state.activeChannelId) return;
  try {
    const data = await api(`/api/channels/${encodeURIComponent(state.activeChannelId)}/poll-vote`, {
      method: "POST",
      body: JSON.stringify({ messageId, optionIndex }),
    });
    upsertMessage(data.message);
  } catch (error) {
    messageInput.setCustomValidity(error.message);
    messageInput.reportValidity();
    setTimeout(() => messageInput.setCustomValidity(""), 2000);
  }
}

function upsertMessage(message) {
  const index = state.messages.findIndex((item) => item.id === message.id);
  if (index >= 0) state.messages[index] = message;
  else state.messages.push(message);
  state.messages.sort((a, b) => a.createdAt - b.createdAt);
  renderMessages(true);
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(timestamp);
}

function nearBottom(node) {
  return node.scrollHeight - node.scrollTop - node.clientHeight < 90;
}

async function openServer(serverId) {
  state.home = false;
  state.dmPeer = null;
  membersEl.hidden = false;
  const detail = await api(`/api/servers/${encodeURIComponent(serverId)}`);
  state.server = detail.server;
  state.channels = detail.channels;
  state.members = detail.members;
  state.activeServerId = serverId;
  state.online = new Map();
  renderRail();
  renderChannels();
  renderMembers();
  connectHub(serverId);
  const keep =
    detail.channels.find((channel) => channel.id === state.activeChannelId) ??
    detail.channels.find((channel) => (channel.kind || "text") !== "voice") ??
    detail.channels[0];
  if (keep) await openChannel(keep.id);
  else {
    state.activeChannelId = null;
    state.messages = [];
    renderTopbar();
    renderMessages(true);
    closeSocket();
  }
}

async function refreshSocial() {
  const [friendsBody, dmsBody] = await Promise.all([
    api("/api/friends"),
    api("/api/dms"),
  ]);
  state.friends = friendsBody.friends || [];
  state.incoming = friendsBody.incoming || [];
  state.outgoing = friendsBody.outgoing || [];
  state.dms = dmsBody.threads || [];
}

async function openHome() {
  if (state.voice.active && !state.voice.channelId?.startsWith("dm:")) {
    await voiceSession.leave();
  }
  state.home = true;
  state.server = null;
  state.channels = [];
  state.members = [];
  state.activeServerId = "home";
  state.activeChannelId = null;
  state.online = new Map();
  closeHub();
  closeSocket();
  membersEl.hidden = true;
  await refreshSocial();
  renderRail();
  renderHomeSidebar();
  renderTopbar();
  renderVoiceStage();
  if (state.dms[0]) await openDmThread(state.dms[0]);
  else {
    state.dmPeer = null;
    composer.hidden = true;
    transcript.replaceChildren(
      el("div", { class: "empty" }, [
        el("h2", {}, [text("Friends & DMs")]),
        el("p", {}, [text("Add friends, then message them here. You can also start a voice call in a DM.")]),
      ]),
    );
  }
}

function renderHomeSidebar() {
  const list = el("ul", { class: "channel-list dm-list" });
  list.append(el("li", { class: "channel-section" }, [text("Friends")]));
  list.append(el("li", {}, [
    el("button", {
      class: "channel-open",
      type: "button",
      onclick: () => openAddFriend(),
    }, [text("Add friend")]),
  ]));
  for (const req of state.incoming) {
    list.append(el("li", { class: "friend-request" }, [
      el("span", { class: "member-name" }, [text(req.displayName)]),
      el("button", {
        class: "ghost",
        type: "button",
        onclick: async () => {
          await api(`/api/friends/${encodeURIComponent(req.id)}`, {
            method: "POST",
            body: JSON.stringify({ action: "accept" }),
          });
          await refreshSocial();
          renderHomeSidebar();
        },
      }, [text("Accept")]),
      el("button", {
        class: "ghost",
        type: "button",
        onclick: async () => {
          await api(`/api/friends/${encodeURIComponent(req.id)}`, {
            method: "POST",
            body: JSON.stringify({ action: "decline" }),
          });
          await refreshSocial();
          renderHomeSidebar();
        },
      }, [text("Decline")]),
    ]));
  }
  for (const friend of state.friends) {
    list.append(el("li", { class: "channel-row" }, [
      el("button", {
        class: "channel-open",
        type: "button",
        onclick: () => openDmWithUser(friend),
      }, [
        avatarNode(friend, "avatar tiny"),
        el("span", { class: "member-name" }, [text(friend.displayName)]),
      ]),
    ]));
  }
  list.append(el("li", { class: "channel-section" }, [text("Direct messages")]));
  for (const thread of state.dms) {
    list.append(el("li", { class: "channel-row" }, [
      el("button", {
        class: "channel-open",
        type: "button",
        "aria-current": state.activeChannelId === thread.id ? "true" : null,
        onclick: () => openDmThread(thread),
      }, [
        avatarNode(thread.user, "avatar tiny"),
        el("span", { class: "member-name" }, [text(thread.user.displayName)]),
      ]),
    ]));
  }
  channelsEl.replaceChildren(
    el("div", { class: "side-head" }, [
      el("div", { class: "side-head-title" }, [el("h2", {}, [text("Home")])]),
      el("button", {
        class: "ghost drawer-close",
        type: "button",
        onclick: closeDrawers,
      }, [text("Close")]),
    ]),
    list,
    el("div", { class: "side-foot" }, [
      el("div", { class: "me-row" }, [
        avatarNode(state.me, "avatar sm"),
        el("div", { class: "me-meta" }, [
          el("strong", {}, [text(state.me.displayName)]),
          el("span", {}, [text(`@${state.me.username}`)]),
        ]),
        el("div", { class: "me-actions" }, [
          el("button", { class: "text-button", type: "button", onclick: () => openProfile(state.me.username, true) }, [text("Profile")]),
          el("button", { class: "text-button", type: "button", onclick: logout }, [text("Log out")]),
        ]),
      ]),
    ]),
  );
}

function openAddFriend() {
  openModal("Add friend", (form) => {
    const username = el("input", { name: "username", maxlength: "33", placeholder: "@username", required: true });
    const error = el("p", { class: "form-error", role: "alert" });
    form.append(
      el("label", {}, [text("Username"), username]),
      el("div", { class: "actions" }, [el("button", { type: "submit" }, [text("Send request")])]),
      error,
    );
    form.onsubmit = async (event) => {
      event.preventDefault();
      error.textContent = "";
      try {
        await api("/api/friends", { method: "POST", body: JSON.stringify({ username: username.value }) });
        modal.close();
        await refreshSocial();
        renderHomeSidebar();
      } catch (err) {
        error.textContent = err.message;
      }
    };
  });
}

async function openDmWithUser(user) {
  const data = await api("/api/dms", {
    method: "POST",
    body: JSON.stringify({ userId: user.id }),
  });
  await refreshSocial();
  await openDmThread(data.thread);
}

async function openDmThread(thread) {
  state.home = true;
  state.dmPeer = thread.user;
  state.activeChannelId = thread.id;
  state.server = { id: "home", name: "Home", isLobby: false, canManage: false };
  membersEl.hidden = true;
  renderHomeSidebar();
  renderTopbar();
  composer.hidden = false;
  messageInput.placeholder = `Message @${thread.user.username}`;
  const data = await api(`/api/channels/${encodeURIComponent(thread.id)}/messages?limit=50`);
  state.messages = data.messages;
  state.hasMore = data.messages.length === 50;
  renderMessages(true);
  renderVoiceStage();
  connect(thread.id);
}

async function openChannel(channelId) {
  if (state.voice.active && state.voice.channelId && state.voice.channelId !== channelId) {
    await voiceSession.leave();
  }
  state.activeChannelId = channelId;
  closeDrawers();
  renderChannels();
  renderTopbar();
  const channel = state.channels.find((item) => item.id === channelId);
  const isVoice = channel?.kind === "voice";
  composer.hidden = isVoice;
  if (isVoice) {
    state.messages = [];
    state.hasMore = false;
    transcript.replaceChildren(
      el("div", { class: "empty voice-empty" }, [
        el("p", {}, [text("Voice channel — use the stage above to join. Text chat lives in text channels.")]),
      ]),
    );
    renderVoiceStage();
    connect(channelId);
    return;
  }
  renderVoiceStage();
  const data = await api(`/api/channels/${encodeURIComponent(channelId)}/messages?limit=50`);
  state.messages = data.messages;
  state.hasMore = data.messages.length === 50;
  renderMessages(true);
  connect(channelId);
}

async function loadOlder() {
  const oldest = state.messages[0];
  if (!oldest || !state.activeChannelId) return;
  const data = await api(`/api/channels/${encodeURIComponent(state.activeChannelId)}/messages?limit=50&before=${oldest.createdAt}`);
  const known = new Set(state.messages.map((message) => message.id));
  const older = data.messages.filter((message) => !known.has(message.id));
  state.messages = [...older, ...state.messages];
  state.hasMore = data.messages.length === 50;
  renderMessages(false);
}

function connect(channelId) {
  const generation = ++socketGeneration;
  closeSocket(false);
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/api/channels/${encodeURIComponent(channelId)}/websocket`);
  const abort = new AbortController();
  state.socket = socket;
  state.socketAbort = abort;
  state.pingTimer = setInterval(() => {
    if (socket.readyState === WebSocket.OPEN) socket.send("ping");
  }, 25000);

  socket.addEventListener("message", (event) => {
    if (generation !== socketGeneration || typeof event.data !== "string" || event.data === "pong") return;
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }
    if (payload.type === "ready" || payload.type === "presence") {
      state.online = new Map((payload.online ?? []).map((person) => [person.userId, person]));
      renderMembers();
      if (payload.type === "ready" && payload.voice) {
        voiceSession.handleSocketMessage({ type: "voice_state", voice: payload.voice });
      }
      return;
    }
    if (voiceSession.handleSocketMessage(payload)) return;
    if (payload.type === "message" && payload.message) addMessage(payload.message);
    if (payload.type === "poll_update" && payload.message) upsertMessage(payload.message);
    if (payload.type === "error" && payload.error) {
      messageInput.setCustomValidity(payload.error);
      messageInput.reportValidity();
      setTimeout(() => messageInput.setCustomValidity(""), 2000);
    }
  }, { signal: abort.signal });

  socket.addEventListener("open", () => {
    if (state.voice.active && state.voice.channelId === channelId) {
      socket.send(JSON.stringify({ type: "voice_join" }));
      if (state.voice.muted) socket.send(JSON.stringify({ type: "voice_mute", muted: true }));
    }
  }, { signal: abort.signal });

  socket.addEventListener("close", () => {
    if (state.pingTimer) {
      clearInterval(state.pingTimer);
      state.pingTimer = null;
    }
    if (generation !== socketGeneration) return;
    setTimeout(() => {
      if (generation === socketGeneration && state.activeChannelId === channelId) connect(channelId);
    }, 1200);
  }, { signal: abort.signal });
}

function closeSocket(bump = true) {
  if (state.voice.active && bump) {
    voiceSession.leave();
  }
  if (bump) socketGeneration += 1;
  if (state.pingTimer) {
    clearInterval(state.pingTimer);
    state.pingTimer = null;
  }
  if (state.socketAbort) {
    state.socketAbort.abort();
    state.socketAbort = null;
  }
  const socket = state.socket;
  state.socket = null;
  if (!socket) return;
  try {
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close(1000, "switch");
    }
  } catch {
    // Already closed.
  }
}

function addMessage(message) {
  if (state.messages.some((item) => item.id === message.id)) return;
  state.messages.push(message);
  state.messages.sort((a, b) => a.createdAt - b.createdAt);
  renderMessages(true);
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = messageInput.value;
  if (!body.trim() || !state.activeChannelId) return;
  messageInput.disabled = true;
  try {
    const data = await api(`/api/channels/${encodeURIComponent(state.activeChannelId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ body }),
    });
    messageInput.value = "";
    messageInput.style.height = "auto";
    addMessage(data.message);
  } catch (error) {
    messageInput.setCustomValidity(error.message);
    messageInput.reportValidity();
    setTimeout(() => messageInput.setCustomValidity(""), 2000);
  } finally {
    messageInput.disabled = false;
    messageInput.focus();
  }
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

messageInput.addEventListener("input", () => {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 160)}px`;
});

async function openProfile(username, editable = false) {
  closeDrawers();
  let profile = state.members.find((member) => member.username === username) || null;
  if (!profile || profile.bio === undefined) {
    try {
      const data = await api(`/api/users/${encodeURIComponent(username)}`);
      profile = data.user;
    } catch (error) {
      openModal("Profile", (form) => {
        form.append(el("p", { class: "form-error" }, [text(error.message)]));
      });
      return;
    }
  }
  if (editable && state.me) {
    openEditProfile(profile);
    return;
  }
  openModal(profile.displayName, (form) => {
    form.append(
      el("div", { class: "profile-card" }, [
        avatarNode(profile, "avatar lg"),
        el("div", {}, [
          el("h3", {}, [text(profile.displayName)]),
          el("p", { class: "handle" }, [text(`@${profile.username}`)]),
          profile.isPlatformOwner ? el("p", { class: "role-pill" }, [text("Hall owner")]) : null,
        ]),
      ]),
      el("p", { class: "bio" }, [text(profile.bio || "No bio yet.")]),
      state.me?.username === profile.username
        ? el("button", { class: "ghost", type: "button", onclick: () => openEditProfile(profile) }, [text("Edit profile")])
        : null,
    );
  });
}

function openEditProfile(profile) {
  openModal("Edit profile", (form) => {
    const previewWrap = el("div", {});
    previewWrap.append(avatarNode(profile, "avatar lg"));
    const bio = el("textarea", {
      name: "bio",
      maxlength: "280",
      rows: "4",
      placeholder: "Short bio",
    });
    bio.value = profile.bio || "";
    const file = el("input", { type: "file", accept: "image/png,image/jpeg,image/webp,image/gif" });
    const error = el("p", { class: "form-error", role: "alert" });
    const status = el("p", { class: "lede" });
    form.append(
      el("div", { class: "profile-card" }, [
        previewWrap,
        el("div", {}, [
          el("h3", {}, [text(profile.displayName)]),
          el("p", { class: "handle" }, [text(`@${profile.username}`)]),
        ]),
      ]),
      el("label", {}, [text("Photo"), file]),
      el("label", {}, [text("Bio"), bio]),
      status,
      error,
      el("div", { class: "actions" }, [
        el("button", {
          class: "ghost",
          type: "button",
          onclick: async () => {
            error.textContent = "";
            try {
              const data = await api("/api/me/avatar", { method: "DELETE" });
              state.me = data.user;
              syncMember(data.user);
              modal.close();
              renderChannels();
              renderMembers();
              renderMessages(false);
            } catch (err) {
              error.textContent = err.message;
            }
          },
        }, [text("Remove photo")]),
        el("button", { type: "submit" }, [text("Save")]),
      ]),
    );
    file.addEventListener("change", async () => {
      const picked = file.files?.[0];
      if (!picked) return;
      error.textContent = "";
      status.textContent = "Uploading…";
      try {
        const response = await fetch("/api/me/avatar", {
          method: "PUT",
          headers: { "content-type": picked.type || "application/octet-stream" },
          body: picked,
          credentials: "same-origin",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Upload failed");
        state.me = data.user;
        syncMember(data.user);
        previewWrap.replaceChildren(avatarNode(data.user, "avatar lg"));
        status.textContent = "Photo updated.";
        renderChannels();
        renderMembers();
        renderMessages(false);
      } catch (err) {
        error.textContent = err.message;
        status.textContent = "";
      } finally {
        file.value = "";
      }
    });
    form.onsubmit = async (event) => {
      event.preventDefault();
      error.textContent = "";
      try {
        const data = await api("/api/me", {
          method: "PATCH",
          body: JSON.stringify({ bio: bio.value }),
        });
        state.me = data.user;
        syncMember(data.user);
        modal.close();
        renderChannels();
        renderMembers();
      } catch (err) {
        error.textContent = err.message;
      }
    };
  });
}

function syncMember(user) {
  state.members = state.members.map((member) => (member.id === user.id ? { ...member, ...user } : member));
}

function openServerSettings() {
  const server = state.server;
  if (!server || !canManageActiveServer()) return;
  openModal("Server settings", (form) => {
    const name = el("input", {
      name: "name",
      maxlength: "80",
      value: server.name,
      required: true,
      disabled: server.isLobby ? "disabled" : null,
    });
    const bio = el("textarea", { name: "bio", maxlength: "280", rows: "3" });
    bio.value = server.bio || "";
    const invite = el("input", {
      name: "invite",
      maxlength: "32",
      value: server.inviteCode,
      disabled: server.isLobby ? "disabled" : null,
    });
    const file = el("input", { type: "file", accept: "image/jpeg,image/png,image/webp,image/gif" });
    const status = el("p", { class: "lede" });
    const error = el("p", { class: "form-error", role: "alert" });
    const preview = server.avatarUrl
      ? el("img", { src: server.avatarUrl, alt: "", class: "server-preview" })
      : el("div", { class: "server-preview letter" }, [text(server.iconLetter)]);
    form.append(
      el("div", { class: "profile-card" }, [preview, el("div", {}, [el("h3", {}, [text(server.name)])])]),
      el("label", {}, [text("Name"), name]),
      el("label", {}, [text("Bio"), bio]),
      el("label", {}, [text("Invite link code (hallchat.lopro.cc/invite/…)"), invite]),
      el("p", { class: "lede" }, [text(inviteLink(server.inviteCode))]),
      el("label", {}, [text("Icon / pfp"), file]),
      status,
      error,
      el("div", { class: "actions" }, [
        el("button", { class: "ghost", type: "button", onclick: () => modal.close() }, [text("Cancel")]),
        el("button", { type: "submit" }, [text("Save")]),
      ]),
    );
    file.addEventListener("change", async () => {
      const picked = file.files?.[0];
      if (!picked) return;
      error.textContent = "";
      status.textContent = "Uploading…";
      try {
        const response = await fetch(`/api/servers/${encodeURIComponent(server.id)}/avatar`, {
          method: "PUT",
          headers: { "content-type": picked.type || "application/octet-stream" },
          body: picked,
          credentials: "same-origin",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Upload failed");
        state.server = data.server;
        state.servers = state.servers.map((item) => (item.id === data.server.id ? { ...item, ...data.server } : item));
        status.textContent = "Icon updated.";
        renderRail();
        renderChannels();
      } catch (err) {
        error.textContent = err.message;
        status.textContent = "";
      } finally {
        file.value = "";
      }
    });
    form.onsubmit = async (event) => {
      event.preventDefault();
      error.textContent = "";
      try {
        const payload = { bio: bio.value };
        if (!server.isLobby) {
          payload.name = name.value;
          payload.inviteCode = invite.value;
        }
        const data = await api(`/api/servers/${encodeURIComponent(server.id)}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        state.server = data.server;
        state.servers = state.servers.map((item) => (item.id === data.server.id ? { ...item, ...data.server } : item));
        modal.close();
        renderRail();
        renderChannels();
        renderTopbar();
      } catch (err) {
        error.textContent = err.message;
      }
    };
  });
}

function openAddMenu() {
  openModal("Add a server", (form) => {
    const name = el("input", { name: "name", maxlength: "80", placeholder: "Server name", required: true });
    const code = el("input", { name: "code", maxlength: "32", placeholder: "Invite code" });
    const error = el("p", { class: "form-error", role: "alert" });
    form.append(
      el("label", {}, [text("Create"), name]),
      el("div", { class: "actions" }, [
        el("button", { type: "submit" }, [text("Create server")]),
      ]),
      el("label", {}, [text("Or paste invite link / code"), code]),
      el("div", { class: "actions" }, [
        el("button", {
          class: "ghost",
          type: "button",
          onclick: async () => {
            error.textContent = "";
            try {
              await joinWith(code.value);
            } catch (err) {
              error.textContent = err.message;
            }
          },
        }, [text("Join")]),
      ]),
      error,
    );
    form.onsubmit = async (event) => {
      event.preventDefault();
      error.textContent = "";
      try {
        const data = await api("/api/servers", { method: "POST", body: JSON.stringify({ name: name.value }) });
        modal.close();
        await refreshAndOpen(data.server.id);
      } catch (err) {
        error.textContent = err.message;
      }
    };
  });
}

async function joinWith(code) {
  const extracted = extractInviteCode(code);
  if (!extracted) throw new Error("Paste an invite link or code");
  const data = await api("/api/join", { method: "POST", body: JSON.stringify({ code: extracted }) });
  modal.close();
  await refreshAndOpen(data.server.id);
}

function openCreateChannel(kind = "text") {
  const voice = kind === "voice";
  openModal(voice ? "Create voice channel" : "Add text channel", (form) => {
    const name = el("input", {
      name: "name",
      maxlength: "32",
      placeholder: voice ? "voice-lounge" : "channel-name",
      required: true,
    });
    const error = el("p", { class: "form-error", role: "alert" });
    form.append(
      el("p", { class: "lede" }, [text(voice ? "People join this VC to talk with mics." : "A normal chat channel.")]),
      el("label", {}, [text("Name"), name]),
      el("div", { class: "actions" }, [el("button", { type: "submit" }, [text(voice ? "Create VC" : "Create")])]),
      error,
    );
    form.onsubmit = async (event) => {
      event.preventDefault();
      error.textContent = "";
      try {
        const data = await api(`/api/servers/${encodeURIComponent(state.activeServerId)}/channels`, {
          method: "POST",
          body: JSON.stringify({ name: name.value, kind: voice ? "voice" : "text" }),
        });
        modal.close();
        await openServer(state.activeServerId);
        await openChannel(data.channel.id);
      } catch (err) {
        error.textContent = err.message;
      }
    };
  });
}

function openModal(title, fill) {
  modalForm.onsubmit = null;
  modalForm.replaceChildren(el("h2", {}, [text(title)]));
  fill(modalForm);
  modalForm.append(el("button", { class: "text-button", type: "button", onclick: () => modal.close() }, [text("Cancel")]));
  if (!modal.open) modal.showModal();
}

async function copyInvite() {
  if (!state.server) return;
  const link = inviteLink(state.server.inviteCode);
  try {
    if (navigator.clipboard) await navigator.clipboard.writeText(link);
  } catch {
    // The invite stays visible if the browser blocks the clipboard.
  }
}

async function leaveServer() {
  if (!state.server || state.server.isLobby) return;
  try {
    await api(`/api/servers/${encodeURIComponent(state.server.id)}/leave`, { method: "POST" });
    state.activeServerId = null;
    state.activeChannelId = null;
    await enterApp();
  } catch (error) {
    authError.textContent = error.message;
  }
}

async function logout() {
  try {
    await api("/api/logout", { method: "POST" });
  } catch {
    // Still clear the local session UI.
  }
  state.me = null;
  state.servers = [];
  state.server = null;
  state.channels = [];
  state.members = [];
  state.messages = [];
  state.online = new Map();
  state.activeServerId = null;
  state.activeChannelId = null;
  state.home = false;
  state.friends = [];
  state.dms = [];
  closeHub();
  setAuthMode("login");
  showAuth();
}

async function refreshAndOpen(serverId) {
  const listed = await api("/api/servers");
  state.servers = listed.servers;
  state.activeChannelId = null;
  await openServer(serverId);
}

async function bootApp() {
  captureInviteFromLocation();
  const inviteCode = pendingInviteCode();
  if (inviteCode && boot.querySelector("p")) boot.querySelector("p").textContent = "Opening invite…";
  try {
    const data = await api("/api/me");
    state.me = data.user;
    await enterApp();
  } catch (error) {
    if (error.status === 401) {
      // Prefer sign-in for invite links — most people already have an account.
      setAuthMode("login");
      showAuth();
      if (inviteCode) {
        authTitle.textContent = "Join with invite";
        authLede.textContent = "Sign in (or create an account) to open that server in Hall.";
      }
    } else {
      setAuthMode("login");
      showAuth();
      authError.textContent = error.message;
    }
  }
}

if (backdrop) {
  backdrop.addEventListener("click", closeDrawers);
}
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawers();
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

if (emojiPanel && emojiButton) {
  for (const emoji of EMOJI_PICKER) {
    emojiPanel.append(el("button", {
      class: "emoji-pick",
      type: "button",
      onclick: () => {
        const start = messageInput.selectionStart ?? messageInput.value.length;
        const end = messageInput.selectionEnd ?? start;
        messageInput.value = `${messageInput.value.slice(0, start)}${emoji}${messageInput.value.slice(end)}`;
        messageInput.focus();
        const caret = start + emoji.length;
        messageInput.setSelectionRange(caret, caret);
        emojiPanel.hidden = true;
      },
    }, [text(emoji)]));
  }
  emojiButton.addEventListener("click", () => {
    emojiPanel.hidden = !emojiPanel.hidden;
  });
  document.addEventListener("click", (event) => {
    if (emojiPanel.hidden) return;
    if (event.target === emojiButton || emojiPanel.contains(event.target)) return;
    emojiPanel.hidden = true;
  });
}

setAuthMode("login");
bootApp();
