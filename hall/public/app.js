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
const replyBar = document.querySelector("#reply-bar");
const mentionMenu = document.querySelector("#mention-menu");
const contextMenu = document.querySelector("#context-menu");

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
  voiceSocket: null,
  voiceSocketAbort: null,
  voicePingTimer: null,
  voice: {
    active: false,
    muted: false,
    sharing: false,
    channelId: null,
    peers: [],
    localScreenStream: null,
    remoteScreens: {},
  },
  voiceRoster: {},
  home: false,
  friends: [],
  incoming: [],
  outgoing: [],
  dms: [],
  dmPeer: null,
  hubSocket: null,
  hubAbort: null,
  hubPing: null,
  replyTo: null,
};

let socketGeneration = 0;
let voiceSocketGeneration = 0;
let hubGeneration = 0;
let voiceUiFrame = 0;
function scheduleVoiceUi(full = false) {
  // Coalesce WebRTC/roster thrash so typing + VC does not rebuild the whole shell every tick.
  if (full) state._voiceUiFull = true;
  if (voiceUiFrame) return;
  voiceUiFrame = requestAnimationFrame(() => {
    voiceUiFrame = 0;
    const fullPass = state._voiceUiFull;
    state._voiceUiFull = false;
    try {
      // Channels/home first — they replaceChildren and would wipe the voice dock.
      if (fullPass) {
        renderTopbar();
        renderMembers();
        if (!state.home) renderChannels();
        else renderHomeSidebar();
      } else {
        renderTopbar();
      }
      renderVoiceStage();
    } catch (error) {
      console.error(JSON.stringify({ event: "voice_ui_render_failed", message: error?.message || "unknown" }));
    }
  });
}

const voiceSession = createVoiceSession({
  getSocket: () => state.voiceSocket || state.socket,
  getMe: () => state.me,
  onState: (next) => {
    const wasActive = state.voice.active;
    const prev = state.voice;
    state.voice = next;
    if (next.channelId) {
      state.voiceRoster = { ...state.voiceRoster, [next.channelId]: next.peers || [] };
    }
    if (wasActive && !next.active) releaseVoiceSocket();
    const rosterChanged =
      prev.active !== next.active ||
      prev.muted !== next.muted ||
      prev.sharing !== next.sharing ||
      prev.channelId !== next.channelId ||
      (prev.peers?.length || 0) !== (next.peers?.length || 0) ||
      JSON.stringify(prev.peers || []) !== JSON.stringify(next.peers || []);
    scheduleVoiceUi(rosterChanged || !wasActive || !next.active);
  },
});

function voiceRosterFor(channelId) {
  if (!channelId) return [];
  if (state.voice.active && state.voice.channelId === channelId) return state.voice.peers || [];
  return state.voiceRoster[channelId] || [];
}

function applyVoiceRoster(channelId, voice) {
  if (!channelId) return;
  const list = Array.isArray(voice) ? voice : [];
  const prev = state.voiceRoster[channelId] || [];
  state.voiceRoster = { ...state.voiceRoster, [channelId]: list };
  if (state.voice.active && state.voice.channelId === channelId) {
    state.voice = { ...state.voice, peers: list };
  }
  const changed = JSON.stringify(prev) !== JSON.stringify(list);
  if (changed) scheduleVoiceUi(true);
}

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
  const { timeoutMs = 15_000, signal: outerSignal, headers: rawHeaders, ...fetchOptions } = options;
  const headers = new Headers(rawHeaders);
  if (fetchOptions.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  if (outerSignal) {
    if (outerSignal.aborted) controller.abort();
    else outerSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  let response;
  try {
    response = await fetch(path, {
      ...fetchOptions,
      headers,
      credentials: "same-origin",
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timer);
    if (error?.name === "AbortError") {
      const timedOut = new Error("Hall took too long to respond. Refresh and try again.");
      timedOut.status = 408;
      throw timedOut;
    }
    throw error;
  }
  clearTimeout(timer);
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
  armNotificationPrompt();
}

function isPhoneClient() {
  return window.matchMedia("(max-width: 800px), (pointer: coarse)").matches
    || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || "");
}

let notificationPromptArmed = false;
let pushSubscribeInFlight = null;

function urlBase64ToUint8Array(base64url) {
  const padded = `${base64url}${"=".repeat((4 - (base64url.length % 4)) % 4)}`;
  const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function ensureServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  try {
    const existing = await navigator.serviceWorker.getRegistration();
    if (existing) return existing;
    return await navigator.serviceWorker.register("/sw.js");
  } catch {
    return null;
  }
}

async function subscribeHallPush() {
  if (!state.me) return false;
  if (!("Notification" in window) || !("PushManager" in window)) return false;
  if (Notification.permission !== "granted") return false;
  if (pushSubscribeInFlight) return pushSubscribeInFlight;
  pushSubscribeInFlight = (async () => {
    try {
      const reg = await ensureServiceWorker();
      if (!reg) return false;
      await navigator.serviceWorker.ready;
      const { publicKey } = await api("/api/push/vapid-key");
      if (!publicKey) return false;
      let subscription = await reg.pushManager.getSubscription();
      if (!subscription) {
        subscription = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey),
        });
      }
      const json = subscription.toJSON();
      if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) return false;
      await api("/api/push/subscribe", {
        method: "POST",
        body: JSON.stringify({
          endpoint: json.endpoint,
          keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
        }),
      });
      return true;
    } catch {
      return false;
    } finally {
      pushSubscribeInFlight = null;
    }
  })();
  return pushSubscribeInFlight;
}

async function requestHallNotifications() {
  if (!("Notification" in window)) return false;
  try {
    let granted = Notification.permission === "granted";
    if (Notification.permission === "denied") return false;
    if (!granted) {
      const result = await Notification.requestPermission();
      granted = result === "granted";
    }
    if (granted) await subscribeHallPush();
    return granted;
  } catch {
    return false;
  }
}

/** Browsers often ignore permission prompts without a tap — arm one on first interaction. */
function armNotificationPrompt() {
  if (!("Notification" in window)) return;
  if (Notification.permission === "granted") {
    subscribeHallPush();
    return;
  }
  if (Notification.permission !== "default" || notificationPromptArmed) return;
  notificationPromptArmed = true;
  const ask = () => {
    document.removeEventListener("pointerdown", ask, true);
    requestHallNotifications();
  };
  document.addEventListener("pointerdown", ask, true);
}

function messageMentionsMe(message) {
  const name = state.me?.username;
  if (!name || !message?.body) return false;
  return new RegExp(`@${name}\\b`, "i").test(message.body);
}

async function maybeNotifyMessage(message) {
  if (!message || message.userId === state.me?.id) return;
  const mentioned = messageMentionsMe(message);
  if (state.server?.notificationsMuted && !mentioned) return;
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  // Fire when backgrounded, or when Hall is open but you’re not looking at this tab.
  if (!document.hidden && document.hasFocus()) return;
  const title = message.displayName || message.username || "Hall";
  const body = String(message.body || "")
    .replace(/^§HALLPOLL§/, "Poll: ")
    .slice(0, 120) || "New message";
  const options = {
    body,
    tag: `hall-msg-${message.id}`,
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    renotify: false,
    data: { url: "/" },
  };
  try {
    const reg = await navigator.serviceWorker?.ready;
    if (reg?.showNotification) {
      await reg.showNotification(title, options);
      return;
    }
  } catch {
    // Fall through to page Notification.
  }
  try {
    const note = new Notification(title, options);
    note.onclick = () => {
      window.focus();
      note.close();
    };
  } catch {
    // Permission can flip mid-session.
  }
}

async function toggleServerNotifications() {
  if (!state.server || state.home) return;
  const next = !state.server.notificationsMuted;
  try {
    const data = await api(`/api/servers/${encodeURIComponent(state.server.id)}/notifications`, {
      method: "PUT",
      body: JSON.stringify({ muted: next }),
    });
    state.server = { ...state.server, notificationsMuted: Boolean(data.muted) };
    renderChannels();
    renderTopbar();
  } catch (error) {
    openModal("Notifications", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message || "Could not update")]));
    });
  }
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
      return;
    }
    if (payload.type === "voice_roster" && payload.channelId) {
      applyVoiceRoster(payload.channelId, payload.voice);
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
        if (isMobileNav()) openDrawer("menu");
        else closeDrawers();
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
  shell?.classList.remove("nav-open", "people-open");
  if (backdrop) {
    backdrop.classList.remove("show");
    backdrop.hidden = true;
  }
  syncMobileNav();
}

function openDrawer(which) {
  closeDrawers();
  if (which === "menu" || which === "channels" || which === "servers") {
    // Mobile: servers + channels together. Desktop/tablet: open the matching panel.
    if (isMobileNav()) {
      rail.classList.add("open");
      channelsEl.classList.add("open");
      shell?.classList.add("nav-open");
    } else if (which === "servers") {
      rail.classList.add("open");
    } else {
      channelsEl.classList.add("open");
    }
  }
  if (which === "members") {
    membersEl.classList.add("open");
    shell?.classList.add("people-open");
  }
  if (backdrop && which) {
    backdrop.hidden = false;
    backdrop.classList.add("show");
  }
  syncMobileNav(which === "menu" || which === "channels" || which === "servers" ? "menu" : which);
}

function isMobileNav() {
  return window.matchMedia("(max-width: 800px)").matches;
}

function syncMobileNav(active) {
  const nav = document.querySelector("#mobile-nav");
  if (!nav) return;
  const current = active
    || (membersEl.classList.contains("open") ? "people" : null)
    || (channelsEl.classList.contains("open") || rail.classList.contains("open") ? "menu" : null)
    || (state.home ? "home" : "chat");
  for (const button of nav.querySelectorAll("[data-nav]")) {
    button.classList.toggle("active", button.dataset.nav === current);
  }
}

function canManageActiveServer() {
  const server = state.server;
  if (!server) return false;
  if (server.canManage != null) return Boolean(server.canManage);
  return server.isLobby ? Boolean(state.me?.isPlatformOwner) : Boolean(server.isOwner || server.isAdmin);
}

function canDeleteMessage(message) {
  if (!message || !state.me) return false;
  if (message.userId === state.me.id) return true;
  if (state.me.isPlatformOwner) return true;
  return canManageActiveServer();
}

function betaBadge(user) {
  if (!user?.isBetaTester) return null;
  return el("span", { class: "beta-badge", title: "Beta tester" }, [text("β")]);
}

function displayNameNodes(user) {
  return [text(user?.displayName || user?.username || "Hall"), betaBadge(user)];
}

function hideContextMenu() {
  if (!contextMenu) return;
  contextMenu.hidden = true;
  contextMenu.replaceChildren();
}

function hideMentionMenu() {
  if (!mentionMenu) return;
  mentionMenu.hidden = true;
  mentionMenu.replaceChildren();
}

function insertMention(username) {
  const value = messageInput.value;
  const caret = messageInput.selectionStart ?? value.length;
  const before = value.slice(0, caret);
  const after = value.slice(caret);
  const replaced = before.replace(/@([A-Za-z0-9_]{0,32})$/, `@${username} `);
  const next = replaced.endsWith(`@${username} `) ? replaced + after : `${before}@${username} ${after}`;
  messageInput.value = next;
  const pos = next.length - after.length;
  messageInput.setSelectionRange(pos, pos);
  messageInput.focus();
  hideMentionMenu();
}

function setReplyTo(message) {
  state.replyTo = message || null;
  if (!replyBar) return;
  if (!message) {
    replyBar.hidden = true;
    replyBar.replaceChildren();
    return;
  }
  replyBar.hidden = false;
  const preview = String(message.body || "").replace(/^§HALLPOLL§/, "Poll: ").slice(0, 80);
  replyBar.replaceChildren(
    el("div", { class: "reply-bar-meta" }, [
      el("strong", {}, [text(`Replying to ${message.displayName || message.username}`)]),
      el("span", {}, [text(preview || "Message")]),
    ]),
    el("button", {
      class: "ghost",
      type: "button",
      "aria-label": "Cancel reply",
      onclick: () => setReplyTo(null),
    }, [text("×")]),
  );
}

function jumpToMessage(messageId) {
  const node = transcript.querySelector(`[data-message-id="${CSS.escape(messageId)}"]`);
  if (!node) return;
  node.scrollIntoView({ behavior: "smooth", block: "center" });
  node.classList.add("flash");
  setTimeout(() => node.classList.remove("flash"), 1200);
}

async function deleteMessage(message) {
  if (!state.activeChannelId || !message?.id || !canDeleteMessage(message)) return;
  try {
    await api(
      `/api/channels/${encodeURIComponent(state.activeChannelId)}/messages/${encodeURIComponent(message.id)}`,
      { method: "DELETE" },
    );
    state.messages = state.messages.filter((item) => item.id !== message.id);
    if (state.replyTo?.id === message.id) setReplyTo(null);
    renderMessages(false);
  } catch (error) {
    openModal("Delete message", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message || "Could not delete")]));
    });
  }
}

async function toggleAdmin(member, makeAdmin) {
  if (!state.server?.id || !member?.id) return;
  try {
    if (makeAdmin) {
      await api(`/api/servers/${encodeURIComponent(state.server.id)}/admins`, {
        method: "POST",
        body: JSON.stringify({ userId: member.id }),
      });
      member.isAdmin = true;
    } else {
      await api(`/api/servers/${encodeURIComponent(state.server.id)}/admins/${encodeURIComponent(member.id)}`, {
        method: "DELETE",
      });
      member.isAdmin = false;
    }
    state.members = state.members.map((item) => (item.id === member.id ? { ...item, isAdmin: member.isAdmin } : item));
    renderMembers();
  } catch (error) {
    openModal("Admins", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message || "Could not update admin")]));
    });
  }
}

async function toggleBeta(member, add) {
  if (!member?.username) return;
  try {
    const data = await api(`/api/users/${encodeURIComponent(member.username)}/beta`, {
      method: "PUT",
      body: JSON.stringify({ beta: add }),
    });
    const next = Boolean(data.user?.isBetaTester);
    if (state.me?.id === member.id) state.me = { ...state.me, isBetaTester: next };
    state.members = state.members.map((item) => (item.id === member.id ? { ...item, isBetaTester: next } : item));
    state.messages = state.messages.map((item) => (
      item.userId === member.id ? { ...item, isBetaTester: next } : item
    ));
    renderMembers();
    renderMessages(false);
    renderChannels();
  } catch (error) {
    openModal("Beta tester", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message || "Could not update")]));
    });
  }
}

function showContextMenu(event, opts) {
  if (!contextMenu) return;
  event.preventDefault();
  const items = [];
  if (opts.member || opts.message) {
    const user = opts.member || {
      id: opts.message.userId,
      username: opts.message.username,
      displayName: opts.message.displayName,
      isBetaTester: opts.message.isBetaTester,
    };
    if (user.username) {
      items.push({
        label: `Ping @${user.username}`,
        run: () => insertMention(user.username),
      });
    }
    if (opts.message) {
      items.push({ label: "Reply", run: () => setReplyTo(opts.message) });
      if (canDeleteMessage(opts.message)) {
        items.push({ label: "Delete message", danger: true, run: () => deleteMessage(opts.message) });
      }
    }
    if (state.server && !state.server.isLobby && state.server.isOwner && user.id && user.id !== state.me?.id) {
      const member = state.members.find((item) => item.id === user.id) || user;
      if (!member.isOwner) {
        if (member.isAdmin) {
          items.push({ label: "Remove admin", danger: true, run: () => toggleAdmin(member, false) });
        } else {
          items.push({ label: "Make admin", run: () => toggleAdmin(member, true) });
        }
      }
    }
    if (state.me?.isPlatformOwner && user.username) {
      const member = state.members.find((item) => item.username === user.username) || user;
      items.push({
        label: member.isBetaTester ? "Remove beta" : "Add beta",
        run: () => toggleBeta(member, !member.isBetaTester),
      });
    }
  }
  if (items.length === 0) return;
  contextMenu.replaceChildren(
    ...items.map((item) => el("button", {
      class: item.danger ? "context-item danger" : "context-item",
      type: "button",
      onclick: () => {
        hideContextMenu();
        item.run();
      },
    }, [text(item.label)])),
  );
  contextMenu.hidden = false;
  const x = event.clientX ?? (event.touches?.[0]?.clientX ?? 16);
  const y = event.clientY ?? (event.touches?.[0]?.clientY ?? 16);
  contextMenu.style.left = `${Math.min(x, window.innerWidth - 180)}px`;
  contextMenu.style.top = `${Math.min(y, window.innerHeight - 12 - items.length * 40)}px`;
}

function bindUserMenu(node, opts) {
  node.addEventListener("contextmenu", (event) => showContextMenu(event, opts));
  let press = 0;
  node.addEventListener("touchstart", () => {
    press = window.setTimeout(() => {
      const fake = { preventDefault() {}, clientX: 24, clientY: 120 };
      showContextMenu(fake, opts);
    }, 480);
  }, { passive: true });
  node.addEventListener("touchend", () => clearTimeout(press));
  node.addEventListener("touchmove", () => clearTimeout(press));
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
        if (state.voice.active && state.voice.channelId === channelId) {
          await voiceSession.leave();
          releaseVoiceSocket();
        }
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
      const roster = isVoice ? voiceRosterFor(channel.id) : [];
      const openChildren = [
        el("span", { class: isVoice ? "hash voice-hash" : "hash" }, [text(isVoice ? "🔊" : "#")]),
        el("span", { class: "channel-label" }, [
          el("span", { class: "channel-name" }, [text(channel.name)]),
          isVoice && roster.length
            ? el("span", { class: "channel-voice-count" }, [
                text(`${roster.length} in voice · ${roster.map((peer) => peer.displayName).join(", ")}`),
              ])
            : null,
        ]),
      ];
      const row = [
        el("button", {
          type: "button",
          class: isVoice ? "channel-open voice-channel-open" : "channel-open",
          "aria-current": channel.id === state.activeChannelId ? "true" : null,
          onclick: () => openChannel(channel.id),
        }, openChildren),
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
  if (!server.isLobby && !server.unleavable) {
    if (server.isOwner) {
      foot.append(el("button", {
        class: "text-button leave-server-btn",
        type: "button",
        onclick: () => confirmLeaveOrDeleteServer(true),
      }, [text("Delete server")]));
    } else {
      foot.append(el("button", {
        class: "text-button leave-server-btn",
        type: "button",
        onclick: () => confirmLeaveOrDeleteServer(false),
      }, [text("Leave server")]));
    }
  }
  const me = el("div", { class: "me-row" }, [
    avatarNode(state.me, "avatar sm"),
    el("div", { class: "me-meta" }, [
      el("strong", {}, displayNameNodes(state.me)),
      el("span", {}, [text(`@${state.me.username}`)]),
    ]),
    el("div", { class: "me-actions" }, [
      el("button", { class: "text-button", type: "button", onclick: () => openProfile(state.me.username, true) }, [text("Profile")]),
      el("button", { class: "text-button", type: "button", onclick: logout }, [text("Log out")]),
    ]),
  ]);
  foot.append(me);
  const headActions = [];
  headActions.push(el("button", {
    class: server.notificationsMuted ? "ghost mute-notifs on" : "ghost mute-notifs",
    type: "button",
    title: server.notificationsMuted ? "Unmute notifications" : "Mute notifications for this server",
    onclick: () => toggleServerNotifications(),
  }, [text(server.notificationsMuted ? "Unmute" : "Mute")]));
  if (!server.isLobby && !server.unleavable) {
    headActions.push(el("button", {
      class: "ghost leave-server-btn mobile-leave-btn",
      type: "button",
      onclick: () => confirmLeaveOrDeleteServer(Boolean(server.isOwner)),
    }, [text(server.isOwner ? "Delete" : "Leave")]));
  }
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
  const voiceCount = voiceRosterFor(state.activeChannelId).length;
  const canLeave = Boolean(state.server && !state.home && !state.server.isLobby && !state.server.unleavable);
  topbar.replaceChildren(
    el("div", { class: "topbar-actions" }, [
      el("button", {
        class: "ghost menu-button",
        type: "button",
        "aria-label": "Open menu",
        onclick: () => openDrawer("menu"),
      }, [text("Menu")]),
    ]),
    el("button", {
      class: "topbar-title linkish",
      type: "button",
      title: "Open menu",
      onclick: () => openDrawer("menu"),
    }, [
      el("h2", {}, [text(title)]),
      el("p", {}, [text(isDm ? "Direct message" : state.home ? "Friends & DMs" : state.server ? state.server.name : "No server")]),
    ]),
    el("div", { class: "topbar-actions topbar-end" }, [
      canLeave
        ? el("button", {
            class: "ghost leave-server-btn mobile-leave-top",
            type: "button",
            "aria-label": state.server.isOwner ? "Delete server" : "Leave server",
            onclick: () => confirmLeaveOrDeleteServer(Boolean(state.server.isOwner)),
          }, [text(state.server.isOwner ? "Delete" : "Leave")])
        : null,
      !state.home && state.server
        ? el("button", {
            class: state.server.notificationsMuted ? "ghost mute-notifs on mobile-mute-top" : "ghost mute-notifs mobile-mute-top",
            type: "button",
            "aria-label": state.server.notificationsMuted ? "Unmute notifications" : "Mute notifications",
            onclick: () => toggleServerNotifications(),
          }, [text(state.server.notificationsMuted ? "Unmute" : "Mute")])
        : null,
      state.activeChannelId && (isVoice || isDm)
        ? el("button", {
            class: inThisVoice ? "ghost voice-button on" : "ghost voice-button",
            type: "button",
            "aria-label": inThisVoice ? "Leave call" : isDm ? "Start call" : "Join voice",
            onclick: () => toggleVoice(),
          }, [text(inThisVoice ? `Call · ${voiceCount}` : isDm ? "Call" : "Voice")])
        : null,
      state.home
        ? el("button", {
            class: "ghost people-button",
            type: "button",
            "aria-label": "Friends menu",
            onclick: () => openDrawer("menu"),
          }, [text("Friends")])
        : el("button", {
            class: "ghost people-button",
            type: "button",
            "aria-label": "Members",
            onclick: () => openDrawer("members"),
          }, [text("People")]),
    ]),
  );
  syncMobileNav();
}

async function toggleScreenShare() {
  try {
    await voiceSession.toggleShare();
  } catch (error) {
    if (error?.name === "NotAllowedError") return;
    openModal("Screen share", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message || "Could not share screen")]));
    });
  }
}

function screenStreamFor(peer) {
  if (peer.userId === state.me?.id) return state.voice.localScreenStream || null;
  return state.voice.remoteScreens?.[peer.userId] || null;
}

/** Persist zoom/pan across voice-stage re-renders. */
const screenZoom = new Map(); // userId -> { scale, x, y }

function screenZoomState(userId) {
  let next = screenZoom.get(userId);
  if (!next) {
    next = { scale: 1, x: 0, y: 0 };
    screenZoom.set(userId, next);
  }
  return next;
}

function clampScreenZoom(view) {
  view.scale = Math.min(6, Math.max(1, view.scale));
  if (view.scale === 1) {
    view.x = 0;
    view.y = 0;
  }
}

function applyScreenTransform(video, userId) {
  const view = screenZoomState(userId);
  clampScreenZoom(view);
  video.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  video.classList.toggle("zoomed", view.scale > 1);
}

function attachScreenZoom(viewport, video, userId, labelEl) {
  const syncLabel = () => {
    if (!labelEl) return;
    const view = screenZoomState(userId);
    labelEl.textContent = view.scale === 1 ? "100%" : `${Math.round(view.scale * 100)}%`;
  };
  const paint = () => {
    applyScreenTransform(video, userId);
    syncLabel();
    viewport.classList.toggle("is-zoomed", screenZoomState(userId).scale > 1);
  };
  paint();

  viewport.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const view = screenZoomState(userId);
      const delta = event.deltaY > 0 ? -0.12 : 0.12;
      view.scale += delta;
      clampScreenZoom(view);
      paint();
    },
    { passive: false },
  );

  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  viewport.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    if (screenZoomState(userId).scale <= 1) return;
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    viewport.setPointerCapture(event.pointerId);
    viewport.classList.add("dragging");
  });
  viewport.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const view = screenZoomState(userId);
    view.x += event.clientX - lastX;
    view.y += event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
    paint();
  });
  const endDrag = (event) => {
    if (!dragging) return;
    dragging = false;
    viewport.classList.remove("dragging");
    try {
      viewport.releasePointerCapture(event.pointerId);
    } catch {
      // ignore
    }
  };
  viewport.addEventListener("pointerup", endDrag);
  viewport.addEventListener("pointercancel", endDrag);

  return {
    zoomIn: () => {
      const view = screenZoomState(userId);
      view.scale += 0.25;
      paint();
    },
    zoomOut: () => {
      const view = screenZoomState(userId);
      view.scale -= 0.25;
      paint();
    },
    reset: () => {
      const view = screenZoomState(userId);
      view.scale = 1;
      view.x = 0;
      view.y = 0;
      paint();
    },
    paint,
  };
}

function openScreenViewer(peer, stream) {
  const existing = document.querySelector("#screen-viewer");
  existing?.remove();
  const video = document.createElement("video");
  video.className = "screen-viewer-video";
  video.autoplay = true;
  video.playsInline = true;
  video.muted = true;
  video.srcObject = stream;
  const zoomLabel = el("span", { class: "screen-zoom-label" }, [text("100%")]);
  const viewport = el("div", { class: "screen-viewer-viewport" }, [video]);
  const controls = attachScreenZoom(viewport, video, `viewer:${peer.userId}`, zoomLabel);
  const overlay = el("div", { id: "screen-viewer", class: "screen-viewer", role: "dialog", "aria-label": "Screen share" }, [
    el("header", { class: "screen-viewer-bar" }, [
      el("strong", {}, [text(`${peer.displayName}'s screen`)]),
      el("div", { class: "screen-viewer-actions" }, [
        el("button", { class: "ghost", type: "button", onclick: () => controls.zoomOut() }, [text("−")]),
        zoomLabel,
        el("button", { class: "ghost", type: "button", onclick: () => controls.zoomIn() }, [text("+")]),
        el("button", { class: "ghost", type: "button", onclick: () => controls.reset() }, [text("Reset")]),
        el("button", {
          class: "ghost",
          type: "button",
          onclick: () => overlay.remove(),
        }, [text("Close")]),
      ]),
    ]),
    viewport,
    el("p", { class: "screen-viewer-hint" }, [text("Scroll to zoom · drag to pan")]),
  ]);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) overlay.remove();
  });
  const onKey = (event) => {
    if (event.key === "Escape") {
      overlay.remove();
      window.removeEventListener("keydown", onKey);
    }
  };
  window.addEventListener("keydown", onKey);
  document.body.append(overlay);
}

function voiceTileFor(peer) {
  const mine = peer.userId === state.me?.id;
  const stream = screenStreamFor(peer);
  // Prefer a live stream even if the roster flag lagged behind WebRTC.
  const isSharing = Boolean(peer.sharing || (mine && state.voice.sharing) || stream);
  const hasShareAudio = Boolean(stream?.getAudioTracks?.().length);
  const status = isSharing
    ? !stream
      ? mine ? "Starting screen share…" : "Connecting to screen…"
      : mine
        ? hasShareAudio
          ? "Sharing screen · 1080p60 · sound"
          : "Sharing screen · 1080p60 — tick Share audio in the picker"
        : "Sharing screen"
    : peer.muted ? "Muted" : mine ? "You" : "In call";
  if (!isSharing) {
    return el("div", {
      class: mine ? "voice-tile me" : "voice-tile",
    }, [
      avatarNode({ ...peer, id: peer.userId }, "avatar lg"),
      el("strong", {}, [text(peer.displayName)]),
      el("span", { class: "voice-tile-status" }, [text(status)]),
    ]);
  }
  if (!stream) {
    return el("div", {
      class: mine ? "voice-tile me" : "voice-tile",
      "data-sharing": "1",
    }, [
      el("div", { class: "voice-screen-viewport waiting" }, [
        avatarNode({ ...peer, id: peer.userId }, "avatar lg"),
        el("p", { class: "voice-screen-wait" }, [text(mine ? "Starting share…" : "Waiting for video…")]),
      ]),
      el("strong", {}, [text(peer.displayName)]),
      el("span", { class: "voice-tile-status" }, [text(status)]),
    ]);
  }

  // Reuse the live <video> so roster/WebRTC ticks do not black the share.
  let video = document.querySelector(`video.voice-screen[data-peer-screen="${CSS.escape(peer.userId)}"]:not(.voice-screen-sink)`);
  if (!video || video.srcObject !== stream) {
    video = document.createElement("video");
    video.className = "voice-screen";
    video.dataset.peerScreen = peer.userId;
    video.autoplay = true;
    video.playsInline = true;
    video.muted = true;
    video.srcObject = stream;
  } else if (video.srcObject !== stream) {
    video.srcObject = stream;
  }
  void video.play().catch(() => {});
  const zoomLabel = el("span", { class: "screen-zoom-label" }, [text("100%")]);
  const viewport = el("div", {
    class: "voice-screen-viewport",
    title: "Scroll to zoom · drag to pan · double-click to expand",
  }, [video]);
  const controls = attachScreenZoom(viewport, video, peer.userId, zoomLabel);
  viewport.addEventListener("dblclick", () => openScreenViewer(peer, stream));

  return el("div", {
    class: mine ? "voice-tile me" : "voice-tile",
    "data-sharing": "1",
  }, [
    viewport,
    el("div", { class: "voice-screen-toolbar" }, [
      el("strong", {}, [text(peer.displayName)]),
      el("div", { class: "voice-screen-zoom" }, [
        el("button", { class: "ghost", type: "button", title: "Zoom out", onclick: () => controls.zoomOut() }, [text("−")]),
        zoomLabel,
        el("button", { class: "ghost", type: "button", title: "Zoom in", onclick: () => controls.zoomIn() }, [text("+")]),
        el("button", { class: "ghost", type: "button", title: "Reset zoom", onclick: () => controls.reset() }, [text("Reset")]),
        el("button", {
          class: "ghost",
          type: "button",
          title: "Expand",
          onclick: () => openScreenViewer(peer, stream),
        }, [text("Expand")]),
      ]),
    ]),
    el("span", { class: "voice-tile-status" }, [text(status)]),
  ]);
}

function renderVoiceStage() {
  const stage = document.querySelector("#voice-stage");
  if (!stage) return;
  try {
    renderVoiceStageInner(stage);
  } catch (error) {
    console.error(JSON.stringify({ event: "voice_stage_render_failed", message: error?.message || "unknown" }));
  }
}

function voiceCallLabel() {
  if (state.voice.channelId?.startsWith("dm:")) {
    return `Call · ${state.dmPeer?.displayName || "DM"}`;
  }
  const voiceChannel = state.channels.find((item) => item.id === state.voice.channelId);
  return `Voice · ${voiceChannel?.name || "channel"}`;
}

function placeVoiceDock(dock) {
  const channels = document.querySelector("#channels");
  if (!channels) return;
  const foot = channels.querySelector(".side-foot");
  if (foot) channels.insertBefore(dock, foot);
  else channels.append(dock);
}

function renderVoiceChrome(minimized) {
  const label = voiceCallLabel();
  const title = state.voice.sharing ? "Sharing screen" : "Voice Connected";
  const detail = state.voice.sharing ? `${label} · 1080p60` : label;

  let dock = document.querySelector("#voice-dock");
  if (state.voice.active) {
    if (!dock) {
      dock = el("div", { id: "voice-dock", class: "voice-dock" });
      placeVoiceDock(dock);
    } else if (!dock.isConnected) {
      placeVoiceDock(dock);
    }
    dock.replaceChildren(
      el("div", { class: "voice-dock-meta" }, [
        el("strong", {}, [text(title)]),
        el("span", {}, [text(detail)]),
      ]),
      el("div", { class: "voice-dock-actions" }, [
        el("button", {
          class: "ghost",
          type: "button",
          onclick: () => voiceSession.toggleMute(),
        }, [text(state.voice.muted ? "Unmute" : "Mute")]),
        el("button", {
          class: state.voice.sharing ? "ghost share-mini on" : "ghost share-mini",
          type: "button",
          onclick: () => toggleScreenShare(),
        }, [text(state.voice.sharing ? "Stop share" : "Share")]),
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

  const mini = document.querySelector("#voice-mini");
  if (!mini) return;
  if (state.voice.active && minimized) {
    mini.hidden = false;
    mini.replaceChildren(
      el("div", { class: "voice-mini-meta" }, [
        el("strong", {}, [text(title)]),
        el("span", {}, [text(detail)]),
      ]),
      el("div", { class: "voice-mini-actions" }, [
        el("button", {
          class: "ghost",
          type: "button",
          onclick: () => voiceSession.toggleMute(),
        }, [text(state.voice.muted ? "Unmute" : "Mute")]),
        el("button", {
          class: "ghost hangup-mini",
          type: "button",
          onclick: () => voiceSession.leave(),
        }, [text("Leave")]),
      ]),
    );
  } else {
    mini.hidden = true;
    mini.replaceChildren();
  }
}

function renderVoiceStageInner(stage) {
  const active = state.channels.find((item) => item.id === state.activeChannelId);
  const voiceChannel = state.channels.find((item) => item.id === state.voice.channelId);
  const viewingOwnCall = Boolean(
    state.voice.active &&
      (state.voice.channelId === state.activeChannelId ||
        (state.home && state.voice.channelId?.startsWith("dm:") && state.activeChannelId?.startsWith("dm:"))),
  );
  // Full stage only on the VC / DM call you’re in. Text chats keep a minimized bar + profile dock.
  const showStage = Boolean(active?.kind === "voice" || viewingOwnCall);
  const channel = voiceChannel
    || active
    || (state.voice.active ? { name: state.dmPeer?.displayName || "Voice", kind: "voice" } : null);

  if (!showStage) {
    stage.hidden = true;
    stage.replaceChildren();
    renderVoiceChrome(true);
    return;
  }

  stage.hidden = false;
  const rosterChannelId = state.voice.active ? state.voice.channelId : state.activeChannelId;
  const peers = voiceRosterFor(rosterChannelId);
  const anyoneSharing = peers.some((peer) => peer.sharing) || state.voice.sharing;
  const tiles = peers.length
    ? peers.map((peer) => voiceTileFor(peer))
    : [
        el("div", { class: "voice-tile empty-tile" }, [
          el("strong", {}, [text(channel?.name || "Voice")]),
          el("span", { class: "voice-tile-status" }, [text("Nobody here yet — join to talk")]),
        ]),
      ];
  stage.replaceChildren(
    el("div", { class: anyoneSharing ? "voice-stage-grid sharing" : "voice-stage-grid" }, tiles),
    el("div", { class: "voice-controls" }, [
      el("button", {
        class: state.voice.muted ? "voice-ctrl mute on" : "voice-ctrl mute",
        type: "button",
        title: state.voice.muted ? "Unmute" : "Mute",
        disabled: !state.voice.active ? "disabled" : null,
        onclick: () => voiceSession.toggleMute(),
      }, [text(state.voice.muted ? "Unmute" : "Mute")]),
      el("button", {
        class: state.voice.sharing ? "voice-ctrl share on" : "voice-ctrl share",
        type: "button",
        title: state.voice.sharing ? "Stop sharing" : "Share screen (1080p60 + sound)",
        disabled: !state.voice.active ? "disabled" : null,
        onclick: () => toggleScreenShare(),
      }, [text(state.voice.sharing ? "Stop share" : "Share")]),
      state.voice.active
        ? el("button", {
            class: "voice-ctrl hangup",
            type: "button",
            title: "Disconnect",
            onclick: () => voiceSession.leave(),
          }, [text("Leave")])
        : el("button", {
            class: "voice-ctrl join",
            type: "button",
            onclick: () => toggleVoice(),
          }, [text("Join")]),
    ]),
  );

  renderVoiceChrome(false);
}

function releaseVoiceSocket() {
  voiceSocketGeneration += 1;
  if (state.voicePingTimer && state.voicePingTimer !== state.pingTimer) {
    clearInterval(state.voicePingTimer);
  }
  state.voicePingTimer = null;
  if (state.voiceSocketAbort && state.voiceSocketAbort !== state.socketAbort) {
    state.voiceSocketAbort.abort();
  }
  state.voiceSocketAbort = null;
  const socket = state.voiceSocket;
  const shared = socket && socket === state.socket;
  state.voiceSocket = null;
  if (!socket || shared) return;
  try {
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close(1000, "voice-end");
    }
  } catch {
    // Already closed.
  }
}

function attachVoiceSocketListeners(socket, channelId, generation, abort) {
  socket.addEventListener("message", (event) => {
    if (generation !== voiceSocketGeneration || typeof event.data !== "string" || event.data === "pong") return;
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }
    if (payload.type === "ready" || payload.type === "presence") {
      if (state.activeChannelId === channelId && Array.isArray(payload.online)) {
        state.online = new Map(payload.online.map((person) => [person.userId, person]));
        renderMembers();
      }
      if (payload.type === "ready" && payload.voice) {
        applyVoiceRoster(channelId, payload.voice);
        voiceSession.handleSocketMessage({ type: "voice_state", voice: payload.voice });
      }
      return;
    }
    if (payload.type === "voice_state") {
      applyVoiceRoster(channelId, payload.voice);
      voiceSession.handleSocketMessage(payload);
      return;
    }
    voiceSession.handleSocketMessage(payload);
  }, { signal: abort.signal });

  socket.addEventListener("close", () => {
    if (state.voicePingTimer && state.voiceSocket === socket && state.voiceSocket !== state.socket) {
      clearInterval(state.voicePingTimer);
      state.voicePingTimer = null;
    }
    if (generation !== voiceSocketGeneration) return;
    if (state.voice.active && state.voice.channelId === channelId && state.voiceSocket !== state.socket) {
      setTimeout(() => {
        if (generation === voiceSocketGeneration && state.voice.active && state.voice.channelId === channelId) {
          openDedicatedVoiceSocket(channelId);
        }
      }, 1200);
    }
  }, { signal: abort.signal });
}

/** Keep the VC websocket when the user browses another channel. */
function promoteSocketToVoice() {
  if (!state.socket || !state.voice.active) return;
  const socket = state.socket;
  const channelId = state.voice.channelId;
  const pingTimer = state.pingTimer;
  const oldAbort = state.socketAbort;

  if (state.voiceSocket && state.voiceSocket !== socket) releaseVoiceSocket();

  state.socket = null;
  state.socketAbort = null;
  state.pingTimer = null;
  socketGeneration += 1;
  // Drop chat listeners; keep the open WebSocket for voice signaling.
  oldAbort?.abort();

  const generation = ++voiceSocketGeneration;
  const abort = new AbortController();
  state.voiceSocket = socket;
  state.voiceSocketAbort = abort;
  state.voicePingTimer = pingTimer;
  attachVoiceSocketListeners(socket, channelId, generation, abort);
}

function bindCurrentSocketAsVoice() {
  if (!state.socket) return;
  if (state.voiceSocket && state.voiceSocket !== state.socket) releaseVoiceSocket();
  state.voiceSocket = state.socket;
  state.voiceSocketAbort = state.socketAbort;
  state.voicePingTimer = state.pingTimer;
}

function openDedicatedVoiceSocket(channelId) {
  const generation = ++voiceSocketGeneration;
  if (state.voiceSocket && state.voiceSocket !== state.socket) {
    try {
      state.voiceSocket.close(1000, "voice-switch");
    } catch {
      // ignore
    }
  }
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/api/channels/${encodeURIComponent(channelId)}/websocket`);
  const abort = new AbortController();
  state.voiceSocket = socket;
  state.voiceSocketAbort = abort;
  state.voicePingTimer = setInterval(() => {
    if (socket.readyState === WebSocket.OPEN) socket.send("ping");
  }, 25000);

  attachVoiceSocketListeners(socket, channelId, generation, abort);

  return new Promise((resolve, reject) => {
    const onOpen = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("Could not stay connected to voice"));
    };
    const cleanup = () => {
      socket.removeEventListener("open", onOpen);
      socket.removeEventListener("error", onError);
    };
    if (socket.readyState === WebSocket.OPEN) {
      resolve();
      return;
    }
    socket.addEventListener("open", onOpen, { once: true });
    socket.addEventListener("error", onError, { once: true });
  });
}

async function joinVoice(channelId) {
  if (state.socket && state.activeChannelId === channelId) {
    bindCurrentSocketAsVoice();
  } else if (!(state.voiceSocket && state.voice.active && state.voice.channelId === channelId)) {
    await openDedicatedVoiceSocket(channelId);
  }
  await voiceSession.join(channelId);
  if (state.socket && state.activeChannelId === channelId) bindCurrentSocketAsVoice();
}

async function toggleVoice() {
  try {
    if (state.voice.active) {
      const viewingOtherVoice =
        state.activeChannelId &&
        state.activeChannelId !== state.voice.channelId &&
        state.channels.find((channel) => channel.id === state.activeChannelId)?.kind === "voice";
      if (viewingOtherVoice) {
        await voiceSession.leave();
        releaseVoiceSocket();
        await joinVoice(state.activeChannelId);
        return;
      }
      await voiceSession.leave();
      releaseVoiceSocket();
      return;
    }
    if (!state.activeChannelId) return;
    await joinVoice(state.activeChannelId);
  } catch (error) {
    openModal("Voice", (form) => {
      form.append(el("p", { class: "form-error" }, [text(error.message || "Could not start voice")]));
    });
  }
}

const MAX_RENDERED_MESSAGES = 250;

function renderMessages(stick) {
  try {
    const wasNearBottom = stick || nearBottom(transcript);
    const frag = document.createDocumentFragment();
    if (state.hasMore || state.messages.length >= MAX_RENDERED_MESSAGES) {
      frag.append(el("button", { class: "ghost load-older", type: "button", onclick: loadOlder }, [text("Load older")]));
    }
    if (state.messages.length === 0) {
      frag.append(el("div", { class: "empty" }, [text("This channel is quiet. Say something.")]));
    }
    const visible = state.messages.length > MAX_RENDERED_MESSAGES
      ? state.messages.slice(-MAX_RENDERED_MESSAGES)
      : state.messages;
    let previous = null;
    for (const message of visible) {
      const author = state.members.find((item) => item.id === message.userId);
      const isBeta = Boolean(message.isBetaTester || author?.isBetaTester);
      const grouped = previous
        && previous.userId === message.userId
        && message.createdAt - previous.createdAt < 5 * 60 * 1000
        && !message.replyTo;
      const avatar = avatarNode(message);
      const header = el("header", {}, [
        el("button", {
          class: "author linkish",
          type: "button",
          onclick: () => openProfile(message.username, message.userId === state.me?.id),
        }, displayNameNodes({ ...message, isBetaTester: isBeta })),
        el("span", { class: "handle" }, [text(`@${message.username}`)]),
        el("time", { class: "time", datetime: formatTimeIso(message.createdAt) }, [text(formatTime(message.createdAt))]),
      ]);
      const reply = message.replyTo
        ? el("button", {
            class: message.replyTo.deleted ? "reply-preview gone" : "reply-preview",
            type: "button",
            onclick: () => message.replyTo.deleted || jumpToMessage(message.replyTo.id),
          }, [
            el("strong", {}, [text(message.replyTo.deleted ? "Deleted message" : message.replyTo.displayName || message.replyTo.username)]),
            el("span", {}, [text(message.replyTo.deleted ? "" : String(message.replyTo.body || "").replace(/^§HALLPOLL§/, "Poll: ").slice(0, 90))]),
          ])
        : null;
      const poll = parsePollBody(message.body);
      const body = poll
        ? renderPoll(message, poll)
        : (() => {
            const node = el("p", { class: "body" });
            appendRichText(node, message.body ?? "");
            return node;
          })();
      const actions = el("div", { class: "message-actions" }, [
        el("button", { class: "ghost", type: "button", title: "Reply", onclick: () => setReplyTo(message) }, [text("Reply")]),
        canDeleteMessage(message)
          ? el("button", { class: "ghost", type: "button", title: "Delete", onclick: () => deleteMessage(message) }, [text("Delete")])
          : null,
      ]);
      const column = el("div", {}, grouped && !poll ? [reply, body, actions] : [header, reply, body, actions]);
      const article = el("article", {
        class: `${grouped && !poll ? "message grouped" : "message"}${poll ? " has-poll" : ""}${messageMentionsMe(message) ? " mentioned" : ""}`,
        "data-message-id": message.id,
      }, [avatar, column]);
      bindUserMenu(article, { message: { ...message, isBetaTester: isBeta } });
      frag.append(article);
      previous = message;
    }
    transcript.replaceChildren(frag);
    if (wasNearBottom) transcript.scrollTop = transcript.scrollHeight;
  } catch (error) {
    console.error(JSON.stringify({ event: "messages_render_failed", message: error?.message || "unknown" }));
  }
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
  const activeRoster = voiceRosterFor(state.activeChannelId);
  const inVoice = new Map(activeRoster.map((peer) => [peer.userId, peer]));
  for (const member of ordered) {
    const online = state.online.has(member.id);
    const voice = inVoice.get(member.id);
    const roleLabel = member.isPlatformOwner
      ? "hall owner"
      : member.isOwner
        ? "owner"
        : member.isAdmin
          ? "admin"
          : null;
    const row = el("li", {
      class: "member-item",
      onclick: () => openProfile(member.username, member.id === state.me?.id),
    }, [
      el("span", { class: online ? "dot on" : "dot" }),
      avatarNode(member, "avatar tiny"),
      el("span", { class: "member-name" }, displayNameNodes(member)),
      voice ? el("span", { class: "role voice-tag" }, [text(voice.muted ? "muted" : "voice")]) : null,
      roleLabel ? el("span", { class: "role" }, [text(roleLabel)]) : null,
    ]);
    bindUserMenu(row, { member });
    list.append(row);
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
  const pattern = /https?:\/\/[^\s<]+|@([A-Za-z0-9_]{2,32})/g;
  let last = 0;
  for (const match of expanded.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > last) node.append(text(expanded.slice(last, index)));
    if (match[0].startsWith("http")) {
      node.append(el("a", { href: match[0], target: "_blank", rel: "noreferrer noopener" }, [text(match[0])]));
    } else {
      const username = match[1]?.toLowerCase();
      const mine = username && username === state.me?.username;
      node.append(el("button", {
        class: mine ? "mention mine" : "mention",
        type: "button",
        onclick: () => username && openProfile(username, mine),
      }, [text(match[0])]));
    }
    last = index + match[0].length;
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
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(date);
}

function formatTimeIso(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString();
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
  // Stay in server VC while browsing Friends — only DM calls are scoped to Home.
  if (
    state.voice.active &&
    state.voice.channelId &&
    !state.voice.channelId.startsWith("dm:") &&
    state.socket &&
    state.activeChannelId === state.voice.channelId
  ) {
    promoteSocketToVoice();
  } else if (state.voice.active && state.voice.channelId?.startsWith("dm:")) {
    await voiceSession.leave();
    releaseVoiceSocket();
  }
  state.home = true;
  state.server = null;
  state.channels = [];
  state.members = [];
  state.activeServerId = "home";
  state.activeChannelId = null;
  state.online = new Map();
  closeHub();
  closeChatSocket();
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
          el("strong", {}, displayNameNodes(state.me)),
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
  const channel = state.channels.find((item) => item.id === channelId);
  const isVoice = channel?.kind === "voice";

  // Joining a different voice channel ends the current call; text channels do not.
  if (state.voice.active && state.voice.channelId !== channelId && isVoice) {
    await voiceSession.leave();
    releaseVoiceSocket();
  } else if (
    state.voice.active &&
    state.voice.channelId === state.activeChannelId &&
    channelId !== state.voice.channelId &&
    state.socket
  ) {
    promoteSocketToVoice();
  }

  state.activeChannelId = channelId;
  closeDrawers();
  renderChannels();
  renderTopbar();
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

function closeChatSocket(bump = true) {
  if (bump) socketGeneration += 1;
  const sharedWithVoice = state.socket && state.socket === state.voiceSocket;
  if (state.pingTimer && !sharedWithVoice) {
    clearInterval(state.pingTimer);
  }
  if (!sharedWithVoice) state.pingTimer = null;
  if (state.socketAbort && !sharedWithVoice) {
    state.socketAbort.abort();
  }
  if (!sharedWithVoice) state.socketAbort = null;
  const socket = state.socket;
  state.socket = null;
  if (!socket || sharedWithVoice) return;
  try {
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close(1000, "switch");
    }
  } catch {
    // Already closed.
  }
}

function connect(channelId) {
  const generation = ++socketGeneration;

  // Already in this VC on a dedicated socket — reuse it for the channel view.
  if (state.voiceSocket && state.voice.channelId === channelId) {
    closeChatSocket(false);
    state.socket = state.voiceSocket;
    state.socketAbort = state.voiceSocketAbort;
    state.pingTimer = state.voicePingTimer;
    return;
  }

  closeChatSocket(false);
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
        applyVoiceRoster(channelId, payload.voice);
        if (state.voice.channelId === channelId) {
          voiceSession.handleSocketMessage({ type: "voice_state", voice: payload.voice });
        }
      }
      return;
    }
    if (payload.type === "voice_state") {
      applyVoiceRoster(channelId, payload.voice);
      if (state.voice.channelId === channelId) voiceSession.handleSocketMessage(payload);
      return;
    }
    if (state.voice.channelId === channelId && voiceSession.handleSocketMessage(payload)) return;
    if (payload.type === "message" && payload.message) addMessage(payload.message);
    if (payload.type === "message_deleted" && payload.messageId) {
      state.messages = state.messages.filter((item) => item.id !== payload.messageId);
      if (state.replyTo?.id === payload.messageId) setReplyTo(null);
      renderMessages(false);
    }
    if (payload.type === "poll_update" && payload.message) upsertMessage(payload.message);
    if (payload.type === "error" && payload.error) {
      messageInput.setCustomValidity(payload.error);
      messageInput.reportValidity();
      setTimeout(() => messageInput.setCustomValidity(""), 2000);
    }
  }, { signal: abort.signal });

  socket.addEventListener("open", () => {
    if (state.voice.active && state.voice.channelId === channelId && state.voiceSocket === socket) {
      socket.send(JSON.stringify({ type: "voice_join" }));
      if (state.voice.muted) socket.send(JSON.stringify({ type: "voice_mute", muted: true }));
    }
  }, { signal: abort.signal });

  socket.addEventListener("close", () => {
    if (state.pingTimer && state.socket === socket) {
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
  if (bump && state.voice.active) {
    voiceSession.leave();
  }
  if (bump) releaseVoiceSocket();
  closeChatSocket(bump);
}

function addMessage(message) {
  if (!message?.id) return;
  if (state.messages.some((item) => item.id === message.id)) return;
  state.messages.push(message);
  state.messages.sort((a, b) => a.createdAt - b.createdAt);
  if (state.messages.length > MAX_RENDERED_MESSAGES * 2) {
    state.messages = state.messages.slice(-MAX_RENDERED_MESSAGES);
    state.hasMore = true;
  }
  renderMessages(true);
  maybeNotifyMessage(message);
}

let composerSending = false;
composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = messageInput.value;
  if (!body.trim() || !state.activeChannelId || composerSending) return;
  composerSending = true;
  messageInput.disabled = true;
  try {
    const data = await api(`/api/channels/${encodeURIComponent(state.activeChannelId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ body, replyTo: state.replyTo?.id || undefined }),
    });
    messageInput.value = "";
    messageInput.style.height = "auto";
    setReplyTo(null);
    hideMentionMenu();
    addMessage(data.message);
  } catch (error) {
    messageInput.setCustomValidity(error.message || "Could not send");
    messageInput.reportValidity();
    setTimeout(() => messageInput.setCustomValidity(""), 2000);
  } finally {
    composerSending = false;
    messageInput.disabled = false;
    messageInput.focus();
  }
});

function updateMentionMenu() {
  if (!mentionMenu) return;
  const caret = messageInput.selectionStart ?? messageInput.value.length;
  const before = messageInput.value.slice(0, caret);
  const match = before.match(/@([A-Za-z0-9_]{0,32})$/);
  if (!match || state.members.length === 0) {
    hideMentionMenu();
    return;
  }
  const query = match[1].toLowerCase();
  const hits = state.members
    .filter((member) => member.username.includes(query) || member.displayName.toLowerCase().includes(query))
    .slice(0, 6);
  if (hits.length === 0) {
    hideMentionMenu();
    return;
  }
  mentionMenu.hidden = false;
  mentionMenu.replaceChildren(
    ...hits.map((member) => el("button", {
      class: "mention-item",
      type: "button",
      onclick: () => insertMention(member.username),
    }, [
      avatarNode(member, "avatar tiny"),
      el("span", {}, displayNameNodes(member)),
      el("span", { class: "handle" }, [text(`@${member.username}`)]),
    ])),
  );
}

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    hideMentionMenu();
    hideContextMenu();
    return;
  }
  if (event.key === "Enter" && !event.shiftKey) {
    const first = mentionMenu && !mentionMenu.hidden ? mentionMenu.querySelector("button") : null;
    if (first) {
      event.preventDefault();
      first.click();
      return;
    }
    event.preventDefault();
    if (!composerSending) composer.requestSubmit();
  }
});

messageInput.addEventListener("input", () => {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 160)}px`;
  updateMentionMenu();
});

document.addEventListener("click", (event) => {
  if (contextMenu && !contextMenu.hidden && !contextMenu.contains(event.target)) hideContextMenu();
  if (mentionMenu && !mentionMenu.hidden && !mentionMenu.contains(event.target) && event.target !== messageInput) {
    hideMentionMenu();
  }
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
          profile.isBetaTester ? el("p", { class: "role-pill beta" }, [text("Beta tester")]) : null,
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
    );
    if (server.isOwner && !server.isLobby) {
      const adminBox = el("div", { class: "admin-list" }, [
        el("p", { class: "lede" }, [text("Admins can edit the server, channels, and delete any message.")]),
      ]);
      for (const member of state.members.filter((item) => !item.isOwner)) {
        adminBox.append(el("div", { class: "admin-row" }, [
          el("span", {}, displayNameNodes(member)),
          el("span", { class: "handle" }, [text(`@${member.username}`)]),
          el("button", {
            class: "ghost",
            type: "button",
            onclick: async () => {
              await toggleAdmin(member, !member.isAdmin);
              openServerSettings();
            },
          }, [text(member.isAdmin ? "Remove admin" : "Make admin")]),
        ]));
      }
      form.append(adminBox);
    }
    form.append(
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

function confirmLeaveOrDeleteServer(asOwner) {
  if (!state.server || state.server.isLobby) return;
  const name = state.server.name || "this server";
  openModal(asOwner ? "Delete server" : "Leave server", (form) => {
    const error = el("p", { class: "form-error", role: "alert" });
    const confirmInput = asOwner
      ? el("input", {
          name: "confirmName",
          maxlength: "80",
          placeholder: name,
          autocomplete: "off",
          required: true,
        })
      : null;
    form.append(
      el("p", { class: "lede" }, [
        text(asOwner
          ? `Delete ${name}? Channels and memberships are removed. This cannot be undone.`
          : `Leave ${name}? You can rejoin later with an invite.`),
      ]),
      asOwner
        ? el("label", {}, [
            text(`Type “${name}” to confirm`),
            confirmInput,
          ])
        : null,
      error,
      el("div", { class: "actions" }, [
        el("button", { class: "ghost", type: "button", onclick: () => modal.close() }, [text("Cancel")]),
        el("button", {
          type: "submit",
          style: "background: var(--danger); color: #1a0d0a;",
        }, [text(asOwner ? "Delete" : "Leave")]),
      ]),
    );
    form.onsubmit = async (event) => {
      event.preventDefault();
      error.textContent = "";
      try {
        if (asOwner) {
          const typed = (confirmInput?.value || "").trim();
          if (typed !== name) {
            error.textContent = "Type the exact server name to delete it";
            return;
          }
          await api(`/api/servers/${encodeURIComponent(state.server.id)}`, {
            method: "DELETE",
            body: JSON.stringify({ confirmName: typed }),
          });
        } else {
          await api(`/api/servers/${encodeURIComponent(state.server.id)}/leave`, { method: "POST" });
        }
        modal.close();
        state.activeServerId = null;
        state.activeChannelId = null;
        state.server = null;
        await enterApp();
      } catch (err) {
        error.textContent = err.message || "Could not leave";
      }
    };
  });
}

async function leaveServer() {
  confirmLeaveOrDeleteServer(Boolean(state.server?.isOwner));
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
    const data = await api("/api/me", { timeoutMs: 12_000 });
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
      authError.textContent = error.message || "Could not reach Hall. Refresh and try again.";
    }
  }
}

if (backdrop) {
  backdrop.addEventListener("click", closeDrawers);
}
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawers();
});

document.querySelector("#mobile-nav")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-nav]");
  if (!button) return;
  const nav = button.dataset.nav;
  if (nav === "menu") {
    openDrawer("menu");
    return;
  }
  if (nav === "home") {
    await openHome();
    openDrawer("menu");
    return;
  }
  if (nav === "chat") {
    closeDrawers();
    syncMobileNav("chat");
    return;
  }
  if (nav === "people") {
    if (state.home) {
      openDrawer("menu");
      return;
    }
    openDrawer("members");
  }
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then(() => {
      if (Notification?.permission === "granted" && state.me) subscribeHallPush();
    }).catch(() => {});
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
