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
      onclick: async () => {
        await openServer(server.id);
        closeDrawers();
        openDrawer("channels");
      },
    }, [text(server.iconLetter)]);
    rail.append(button);
  }
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
  return server.isLobby ? Boolean(state.me?.isPlatformOwner) : Boolean(server.isOwner || state.me?.isPlatformOwner);
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
  state.channels.forEach((channel, index) => {
    const row = [
      el("button", {
        type: "button",
        class: "channel-open",
        "aria-current": channel.id === state.activeChannelId ? "true" : null,
        onclick: () => openChannel(channel.id),
      }, [el("span", { class: "hash" }, [text("#")]), text(channel.name)]),
    ];
    if (manage) {
      row.push(el("div", { class: "channel-move" }, [
        el("button", {
          class: "ghost channel-move-btn",
          type: "button",
          "aria-label": "Move up",
          disabled: index === 0 ? "disabled" : null,
          onclick: () => moveChannel(channel.id, -1),
        }, [text("↑")]),
        el("button", {
          class: "ghost channel-move-btn",
          type: "button",
          "aria-label": "Move down",
          disabled: index === state.channels.length - 1 ? "disabled" : null,
          onclick: () => moveChannel(channel.id, 1),
        }, [text("↓")]),
      ]));
    }
    list.append(el("li", { class: manage ? "channel-row manage" : "channel-row" }, row));
  });
  const foot = el("div", { class: "side-foot" });
  const invite = el("div", { class: "invite" }, [
    text("Invite "),
    el("code", {}, [text(server.inviteCode)]),
  ]);
  invite.append(el("button", { class: "ghost", type: "button", onclick: copyInvite }, [text("Copy")]));
  foot.append(invite);
  if (manage) {
    foot.append(el("button", { class: "ghost", type: "button", onclick: openCreateChannel }, [text("Add channel")]));
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
  channelsEl.replaceChildren(
    el("div", { class: "side-head" }, [
      el("h2", {}, [text(server.name)]),
      el("button", {
        class: "ghost drawer-close",
        type: "button",
        "aria-label": "Close",
        onclick: closeDrawers,
      }, [text("Close")]),
    ]),
    list,
    foot,
  );
}

function renderTopbar() {
  const channel = state.channels.find((item) => item.id === state.activeChannelId);
  const title = channel ? `#${channel.name}` : "Hall";
  messageInput.placeholder = channel ? `Message #${channel.name}` : "Message";
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
        "aria-label": "Channels",
        onclick: () => openDrawer("channels"),
      }, [text("#")]),
    ]),
    el("div", { class: "topbar-title" }, [
      el("h2", {}, [text(title)]),
      el("p", {}, [text(state.server ? state.server.name : "No server")]),
    ]),
    el("button", {
      class: "ghost people-button",
      type: "button",
      "aria-label": "Members",
      onclick: () => openDrawer("members"),
    }, [text("People")]),
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
    const roleLabel = member.isPlatformOwner ? "hall owner" : member.isOwner ? "owner" : null;
    list.append(el("li", {
      class: "member-item",
      onclick: () => openProfile(member.username, member.id === state.me?.id),
    }, [
      el("span", { class: online ? "dot on" : "dot" }),
      avatarNode(member, "avatar tiny"),
      el("span", { class: "member-name" }, [text(member.displayName)]),
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
  closeDrawers();
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
    if (error.status === 401) {
      setAuthMode("login");
      showAuth();
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

setAuthMode("login");
bootApp();
