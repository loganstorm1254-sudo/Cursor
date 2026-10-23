const auth = document.querySelector("#auth");
const authForm = document.querySelector("#auth-form");
const authTitle = document.querySelector("#auth-title");
const authLede = document.querySelector("#auth-lede");
const authError = document.querySelector("#auth-error");
const authSubmit = document.querySelector("#auth-submit");
const authSwitch = document.querySelector("#auth-switch");
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
const modal = document.querySelector("#modal");
const modalForm = document.querySelector("#modal-form");

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
};

let socketGeneration = 0;

function hue(name) {
  let hash = 0;
  for (const char of name) hash = (hash * 33 + char.charCodeAt(0)) >>> 0;
  return hash % 360;
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
}

authSwitch.addEventListener("click", () => setAuthMode(state.mode === "register" ? "login" : "register"));

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

async function enterApp() {
  showApp();
  const listed = await api("/api/servers");
  state.servers = listed.servers;
  renderRail();
  const preferred =
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

function renderRail() {
  rail.replaceChildren();
  for (const server of state.servers) {
    const button = el("button", {
      class: "server-button",
      type: "button",
      title: server.name,
      "aria-current": server.id === state.activeServerId ? "true" : null,
      onclick: () => openServer(server.id),
    }, [text(server.iconLetter)]);
    rail.append(button);
  }
  rail.append(el("button", {
    class: "add-server",
    type: "button",
    title: "Add a server",
    "aria-label": "Add a server",
    onclick: openAddMenu,
  }, [text("+")]));
}

function renderChannels() {
  const server = state.server;
  channelsEl.classList.remove("open");
  if (!server) {
    channelsEl.replaceChildren(el("div", { class: "empty" }, [text("Create or join a server to start talking.")]));
    return;
  }
  const list = el("ul", { class: "channel-list" });
  for (const channel of state.channels) {
    list.append(el("li", {}, [
      el("button", {
        type: "button",
        "aria-current": channel.id === state.activeChannelId ? "true" : null,
        onclick: () => openChannel(channel.id),
      }, [el("span", { class: "hash" }, [text("#")]), text(channel.name)]),
    ]));
  }
  const foot = el("div", { class: "side-foot" });
  const invite = el("div", { class: "invite" }, [
    text("Invite "),
    el("code", {}, [text(server.inviteCode)]),
  ]);
  invite.append(el("button", { class: "ghost", type: "button", onclick: copyInvite }, [text("Copy")]));
  foot.append(invite);
  if (server.isOwner || server.isLobby) {
    foot.append(el("button", { class: "ghost", type: "button", onclick: openCreateChannel }, [text("Add channel")]));
  }
  if (!server.isOwner && !server.isLobby) {
    foot.append(el("button", { class: "text-button", type: "button", onclick: leaveServer }, [text("Leave server")]));
  }
  const me = el("div", { class: "invite" }, [
    text(`@${state.me.username}`),
    el("button", { class: "text-button", type: "button", onclick: logout }, [text("Log out")]),
  ]);
  foot.append(me);
  channelsEl.replaceChildren(
    el("div", { class: "side-head" }, [el("h2", {}, [text(server.name)])]),
    list,
    foot,
  );
}

function renderTopbar() {
  const channel = state.channels.find((item) => item.id === state.activeChannelId);
  const title = channel ? `#${channel.name}` : "Hall";
  messageInput.placeholder = channel ? `Message #${channel.name}` : "Message";
  topbar.replaceChildren(
    el("button", { class: "ghost menu-button", type: "button", onclick: () => channelsEl.classList.toggle("open") }, [text("Channels")]),
    el("div", {}, [
      el("h2", {}, [text(title)]),
      el("p", {}, [text(state.server ? state.server.name : "No server")]),
    ]),
  );
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
    const avatar = el("div", {
      class: "avatar",
      style: `background: hsl(${hue(message.username)} 62% 62%)`,
    }, [text(message.displayName.slice(0, 1).toUpperCase())]);
    const header = el("header", {}, [
      el("span", { class: "author" }, [text(message.displayName)]),
      el("span", { class: "handle" }, [text(`@${message.username}`)]),
      el("time", { class: "time", datetime: new Date(message.createdAt).toISOString() }, [text(formatTime(message.createdAt))]),
    ]);
    const body = el("p", { class: "body" });
    appendRichText(body, message.body);
    const column = el("div", {}, grouped ? [body] : [header, body]);
    nodes.push(el("article", { class: grouped ? "message grouped" : "message" }, [avatar, column]));
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
  for (const member of ordered) {
    const online = state.online.has(member.id);
    list.append(el("li", {}, [
      el("span", { class: online ? "dot on" : "dot" }),
      text(member.displayName),
      member.isOwner ? el("span", { class: "role" }, [text("owner")]) : null,
    ]));
  }
  membersEl.replaceChildren(
    el("div", { class: "side-head" }, [el("h2", {}, [text(`Online — ${onlineCount}`)])]),
    list,
  );
}

function appendRichText(node, value) {
  const pattern = /https?:\/\/[^\s<]+/g;
  let last = 0;
  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > last) node.append(text(value.slice(last, index)));
    const href = match[0];
    node.append(el("a", { href, target: "_blank", rel: "noreferrer noopener" }, [text(href)]));
    last = index + href.length;
  }
  if (last < value.length) node.append(text(value.slice(last)));
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(timestamp);
}

function nearBottom(node) {
  return node.scrollHeight - node.scrollTop - node.clientHeight < 90;
}

async function openServer(serverId) {
  const detail = await api(`/api/servers/${encodeURIComponent(serverId)}`);
  state.server = detail.server;
  state.channels = detail.channels;
  state.members = detail.members;
  state.activeServerId = serverId;
  state.online = new Map();
  renderRail();
  renderChannels();
  renderMembers();
  const keep =
    detail.channels.find((channel) => channel.id === state.activeChannelId) ??
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

async function openChannel(channelId) {
  state.activeChannelId = channelId;
  channelsEl.classList.remove("open");
  renderChannels();
  renderTopbar();
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
      return;
    }
    if (payload.type === "message" && payload.message) addMessage(payload.message);
    if (payload.type === "error" && payload.error) {
      messageInput.setCustomValidity(payload.error);
      messageInput.reportValidity();
      setTimeout(() => messageInput.setCustomValidity(""), 2000);
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
      el("label", {}, [text("Or join with an invite"), code]),
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
  const data = await api("/api/join", { method: "POST", body: JSON.stringify({ code }) });
  modal.close();
  await refreshAndOpen(data.server.id);
}

function openCreateChannel() {
  openModal("Add a channel", (form) => {
    const name = el("input", { name: "name", maxlength: "32", placeholder: "channel-name", required: true });
    const error = el("p", { class: "form-error", role: "alert" });
    form.append(
      el("label", {}, [text("Name"), name]),
      el("div", { class: "actions" }, [el("button", { type: "submit" }, [text("Create")])]),
      error,
    );
    form.onsubmit = async (event) => {
      event.preventDefault();
      error.textContent = "";
      try {
        const data = await api(`/api/servers/${encodeURIComponent(state.activeServerId)}/channels`, {
          method: "POST",
          body: JSON.stringify({ name: name.value }),
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
  if (!state.server || !navigator.clipboard) return;
  try {
    await navigator.clipboard.writeText(state.server.inviteCode);
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
  try {
    const data = await api("/api/me");
    state.me = data.user;
    await enterApp();
  } catch (error) {
    if (error.status === 401) showAuth();
    else {
      showAuth();
      authError.textContent = error.message;
    }
  }
}

setAuthMode("register");
bootApp();
