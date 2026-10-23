import {
  clearSessionHeaders,
  createSession,
  destroySession,
  findUserById,
  findUserByUsername,
  hashPassword,
  passwordMatches,
  requireUser,
  sessionHeaders,
  toPublicUser,
  type PublicUser,
} from "./auth";
import { type ChatMessage } from "./channel";
import { HttpError, asRecord, asString, json, readJson } from "./http";
import { ensureReady } from "./schema";
import {
  iconLetter,
  isPlatformOwnerUsername,
  normalizeBio,
  normalizeChannelName,
  normalizePassword,
  normalizeServerName,
  normalizeUsername,
} from "./username";

export { ChannelRoom } from "./channel";

const MAX_AVATAR_BYTES = 512_000;
const AVATAR_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

type ServerRow = {
  id: string;
  name: string;
  icon_letter: string;
  owner_id: string;
  invite_code: string;
};

type ChannelRow = {
  id: string;
  server_id: string;
  name: string;
  position: number;
  owner_id: string;
};

function publicServer(row: ServerRow, userId: string) {
  return {
    id: row.id,
    name: row.name,
    iconLetter: row.icon_letter,
    inviteCode: row.invite_code,
    ownerId: row.owner_id,
    isOwner: row.owner_id === userId,
    isLobby: row.id === "lobby",
  };
}

async function memberOf(env: Env, serverId: string, userId: string): Promise<boolean> {
  const row = await env.DB.prepare("SELECT 1 AS ok FROM memberships WHERE server_id = ? AND user_id = ?")
    .bind(serverId, userId)
    .first<{ ok: number }>();
  return Boolean(row);
}

async function getChannel(env: Env, channelId: string): Promise<ChannelRow | null> {
  return env.DB.prepare(
    `SELECT c.id, c.server_id, c.name, c.position, s.owner_id
     FROM channels c
     JOIN servers s ON s.id = c.server_id
     WHERE c.id = ?`,
  )
    .bind(channelId)
    .first<ChannelRow>();
}

async function requireChannelMember(env: Env, channelId: string, user: PublicUser): Promise<ChannelRow> {
  const channel = await getChannel(env, channelId);
  if (!channel) throw new HttpError(404, "Channel not found");
  if (!(await memberOf(env, channel.server_id, user.id))) {
    throw new HttpError(403, "You are not in this server");
  }
  return channel;
}

function room(env: Env, channelId: string) {
  return env.CHANNELS.getByName(channelId);
}

async function register(request: Request, env: Env): Promise<Response> {
  const body = asRecord(await readJson(request, 4_096));
  const parsedName = normalizeUsername(asString(body.username, "Username"));
  if ("error" in parsedName) throw new HttpError(403, parsedName.error);
  const parsedPassword = normalizePassword(asString(body.password, "Password"));
  if (typeof parsedPassword !== "string") throw new HttpError(400, parsedPassword.error);

  if (isPlatformOwnerUsername(parsedName.username)) {
    throw new HttpError(403, "Sign in as owner — that account is already set up.");
  }

  const existing = await findUserByUsername(env, parsedName.username);
  if (existing) throw new HttpError(409, "That username is taken");

  const userId = crypto.randomUUID();
  const passwordHash = await hashPassword(parsedPassword);
  const now = Date.now();
  const role = isPlatformOwnerUsername(parsedName.username) ? "owner" : "user";
  try {
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO users (id, username, display_name, password_hash, created_at, bio, avatar_key, role)
         VALUES (?, ?, ?, ?, ?, '', NULL, ?)`,
      ).bind(userId, parsedName.username, parsedName.displayName, passwordHash, now, role),
      env.DB.prepare(
        `INSERT OR IGNORE INTO memberships (server_id, user_id, joined_at)
         VALUES ('lobby', ?, ?)`,
      ).bind(userId, now),
    ]);
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.includes("UNIQUE")) throw new HttpError(409, "That username is taken");
    throw error;
  }

  const token = await createSession(env, userId);
  console.log(JSON.stringify({ event: "register", username: parsedName.username }));
  return json(
    {
      user: toPublicUser({
        id: userId,
        username: parsedName.username,
        display_name: parsedName.displayName,
        bio: "",
        avatar_key: null,
        role,
      }),
    },
    201,
    sessionHeaders(token, request),
  );
}

async function login(request: Request, env: Env): Promise<Response> {
  const body = asRecord(await readJson(request, 4_096));
  const parsedName = normalizeUsername(asString(body.username, "Username"));
  const password = asString(body.password, "Password");
  if ("error" in parsedName) throw new HttpError(401, "Wrong username or password");

  const user = await findUserByUsername(env, parsedName.username);
  const valid = await passwordMatches(password, user?.password_hash ?? null);
  if (!user || !valid) throw new HttpError(401, "Wrong username or password");

  if (isPlatformOwnerUsername(user.username) && user.role !== "owner") {
    await env.DB.prepare(`UPDATE users SET role = 'owner', display_name = 'owner' WHERE id = ?`).bind(user.id).run();
    user.role = "owner";
    user.display_name = "owner";
  }

  await env.DB.prepare("DELETE FROM sessions WHERE user_id = ? AND expires_at < ?").bind(user.id, Date.now()).run();
  const token = await createSession(env, user.id);
  console.log(JSON.stringify({ event: "login", username: user.username }));
  return json({ user: toPublicUser(user) }, 200, sessionHeaders(token, request));
}

async function updateProfile(request: Request, env: Env, user: PublicUser): Promise<Response> {
  const body = asRecord(await readJson(request, 4_096));
  let bio = user.bio;
  if (body.bio !== undefined) {
    const parsed = normalizeBio(asString(body.bio, "Bio"));
    if (typeof parsed !== "string") throw new HttpError(400, parsed.error);
    bio = parsed;
  }
  await env.DB.prepare(`UPDATE users SET bio = ? WHERE id = ?`).bind(bio, user.id).run();
  const row = await findUserById(env, user.id);
  if (!row) throw new HttpError(404, "User not found");
  return json({ user: toPublicUser(row) });
}

async function uploadAvatar(request: Request, env: Env, user: PublicUser): Promise<Response> {
  const type = (request.headers.get("content-type") ?? "").split(";")[0]?.trim().toLowerCase() ?? "";
  if (!AVATAR_TYPES.has(type)) throw new HttpError(415, "Use a JPEG, PNG, WebP, or GIF image");
  const bytes = await request.arrayBuffer();
  if (bytes.byteLength === 0) throw new HttpError(400, "Empty image");
  if (bytes.byteLength > MAX_AVATAR_BYTES) throw new HttpError(413, "Image must be under 512KB");

  const key = `${user.id}/${crypto.randomUUID()}`;
  await env.AVATARS.put(key, bytes, {
    httpMetadata: { contentType: type, cacheControl: "public, max-age=31536000, immutable" },
  });

  const previous = await findUserById(env, user.id);
  await env.DB.prepare(`UPDATE users SET avatar_key = ? WHERE id = ?`).bind(key, user.id).run();
  if (previous?.avatar_key && previous.avatar_key !== key) {
    try {
      await env.AVATARS.delete(previous.avatar_key);
    } catch {
      // Best-effort cleanup.
    }
  }

  const row = await findUserById(env, user.id);
  if (!row) throw new HttpError(404, "User not found");
  return json({ user: toPublicUser(row) });
}

async function clearAvatar(env: Env, user: PublicUser): Promise<Response> {
  const previous = await findUserById(env, user.id);
  await env.DB.prepare(`UPDATE users SET avatar_key = NULL WHERE id = ?`).bind(user.id).run();
  if (previous?.avatar_key) {
    try {
      await env.AVATARS.delete(previous.avatar_key);
    } catch {
      // Best-effort cleanup.
    }
  }
  const row = await findUserById(env, user.id);
  if (!row) throw new HttpError(404, "User not found");
  return json({ user: toPublicUser(row) });
}

async function getAvatar(env: Env, keyPath: string): Promise<Response> {
  const key = decodeURIComponent(keyPath);
  if (!key || key.includes("..") || key.startsWith("/")) throw new HttpError(400, "Bad avatar");
  const object = await env.AVATARS.get(key);
  if (!object) throw new HttpError(404, "Avatar not found");
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("cache-control", "public, max-age=31536000, immutable");
  headers.set("etag", object.httpEtag);
  return new Response(object.body, { headers });
}

async function getProfile(env: Env, usernameRaw: string): Promise<Response> {
  const parsed = normalizeUsername(usernameRaw);
  if ("error" in parsed) throw new HttpError(404, "User not found");
  const row = await findUserByUsername(env, parsed.username);
  if (!row || row.id === "system") throw new HttpError(404, "User not found");
  return json({ user: toPublicUser(row) });
}

async function listServers(env: Env, user: PublicUser): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT s.id, s.name, s.icon_letter, s.owner_id, s.invite_code
     FROM memberships m
     JOIN servers s ON s.id = m.server_id
     WHERE m.user_id = ?
     ORDER BY m.joined_at ASC`,
  )
    .bind(user.id)
    .all<ServerRow>();
  return json({ servers: (results ?? []).map((row) => publicServer(row, user.id)) });
}

async function createServer(request: Request, env: Env, user: PublicUser): Promise<Response> {
  const body = asRecord(await readJson(request, 4_096));
  const name = normalizeServerName(asString(body.name, "Server name"));
  if (!name) throw new HttpError(400, "Server names are 1–80 characters");

  for (let attempt = 0; attempt < 5; attempt++) {
    const serverId = crypto.randomUUID();
    const channelId = crypto.randomUUID();
    const inviteCode = inviteToken();
    const now = Date.now();
    try {
      await env.DB.batch([
        env.DB.prepare(
          `INSERT INTO servers (id, name, icon_letter, owner_id, invite_code, created_at)
           VALUES (?, ?, ?, ?, ?, ?)`,
        ).bind(serverId, name, iconLetter(name), user.id, inviteCode, now),
        env.DB.prepare(
          `INSERT INTO channels (id, server_id, name, position, created_at)
           VALUES (?, ?, 'general', 0, ?)`,
        ).bind(channelId, serverId, now),
        env.DB.prepare(
          `INSERT INTO memberships (server_id, user_id, joined_at)
           VALUES (?, ?, ?)`,
        ).bind(serverId, user.id, now),
      ]);
      console.log(JSON.stringify({ event: "server_created", serverId, userId: user.id }));
      return json(
        {
          server: publicServer(
            { id: serverId, name, icon_letter: iconLetter(name), owner_id: user.id, invite_code: inviteCode },
            user.id,
          ),
          channel: { id: channelId, name: "general", position: 0 },
        },
        201,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "";
      if (message.includes("servers.invite_code")) continue;
      throw error;
    }
  }
  throw new HttpError(503, "Could not create a server. Try again.");
}

function inviteToken(): string {
  const alphabet = "abcdefghjkmnpqrstuvwxyz23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  let code = "";
  for (const byte of bytes) code += alphabet[byte % alphabet.length];
  return code;
}

async function joinServer(request: Request, env: Env, user: PublicUser): Promise<Response> {
  const body = asRecord(await readJson(request, 2_048));
  const code = asString(body.code, "Invite code").trim().toLowerCase();
  if (!/^[a-z0-9]{2,32}$/.test(code)) throw new HttpError(400, "That invite code is not valid");
  const server = await env.DB.prepare(
    "SELECT id, name, icon_letter, owner_id, invite_code FROM servers WHERE invite_code = ?",
  )
    .bind(code)
    .first<ServerRow>();
  if (!server) throw new HttpError(404, "No server uses that invite");
  await env.DB.prepare(
    `INSERT OR IGNORE INTO memberships (server_id, user_id, joined_at)
     VALUES (?, ?, ?)`,
  )
    .bind(server.id, user.id, Date.now())
    .run();
  return json({ server: publicServer(server, user.id) });
}

async function serverDetail(env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare(
    "SELECT id, name, icon_letter, owner_id, invite_code FROM servers WHERE id = ?",
  )
    .bind(serverId)
    .first<ServerRow>();
  if (!server) throw new HttpError(404, "Server not found");
  if (!(await memberOf(env, server.id, user.id))) throw new HttpError(403, "You are not in this server");

  const channels = await env.DB.prepare(
    `SELECT id, name, position
     FROM channels
     WHERE server_id = ?
     ORDER BY position ASC, name ASC`,
  )
    .bind(server.id)
    .all<{ id: string; name: string; position: number }>();
  const members = await env.DB.prepare(
    `SELECT u.id, u.username, u.display_name, u.bio, u.avatar_key, u.role
     FROM memberships m
     JOIN users u ON u.id = m.user_id
     WHERE m.server_id = ? AND u.id != 'system'
     ORDER BY u.display_name COLLATE NOCASE ASC`,
  )
    .bind(server.id)
    .all<{
      id: string;
      username: string;
      display_name: string;
      bio: string | null;
      avatar_key: string | null;
      role: string | null;
    }>();

  return json({
    server: publicServer(server, user.id),
    channels: channels.results ?? [],
    members: (members.results ?? []).map((member) => {
      const profile = toPublicUser(member);
      return {
        ...profile,
        isOwner: member.id === server.owner_id,
      };
    }),
  });
}

async function createChannel(request: Request, env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare("SELECT id, owner_id FROM servers WHERE id = ?")
    .bind(serverId)
    .first<{ id: string; owner_id: string }>();
  if (!server) throw new HttpError(404, "Server not found");
  if (!(await memberOf(env, server.id, user.id))) throw new HttpError(403, "You are not in this server");
  const canCreate = server.owner_id === user.id || server.owner_id === "system" || user.isPlatformOwner;
  if (!canCreate) throw new HttpError(403, "Only the server owner can add channels");

  const body = asRecord(await readJson(request, 2_048));
  const name = normalizeChannelName(asString(body.name, "Channel name"));
  if (!name) throw new HttpError(400, "Channel names use letters, numbers, and hyphens");

  const positionRow = await env.DB.prepare(
    "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM channels WHERE server_id = ?",
  )
    .bind(server.id)
    .first<{ next: number }>();
  const channelId = crypto.randomUUID();
  const now = Date.now();
  try {
    await env.DB.prepare(
      `INSERT INTO channels (id, server_id, name, position, created_at)
       VALUES (?, ?, ?, ?, ?)`,
    )
      .bind(channelId, server.id, name, positionRow?.next ?? 0, now)
      .run();
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.includes("UNIQUE")) throw new HttpError(409, "That channel already exists");
    throw error;
  }
  return json({ channel: { id: channelId, name, position: positionRow?.next ?? 0 } }, 201);
}

async function leaveServer(env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare("SELECT id, owner_id FROM servers WHERE id = ?")
    .bind(serverId)
    .first<{ id: string; owner_id: string }>();
  if (!server) throw new HttpError(404, "Server not found");
  if (server.id === "lobby") throw new HttpError(400, "Everyone stays in Lobby");
  if (server.owner_id === user.id) throw new HttpError(400, "The server owner stays with the server");
  await env.DB.prepare("DELETE FROM memberships WHERE server_id = ? AND user_id = ?").bind(server.id, user.id).run();
  return json({ ok: true });
}

async function listMessages(url: URL, env: Env, user: PublicUser, channelId: string): Promise<Response> {
  await requireChannelMember(env, channelId, user);
  const limit = Number(url.searchParams.get("limit") ?? "50");
  const beforeRaw = url.searchParams.get("before");
  const before = beforeRaw === null || beforeRaw === "" ? null : Number(beforeRaw);
  if (!Number.isFinite(limit) || limit < 1 || limit > 100) throw new HttpError(400, "Limit must be 1–100");
  if (before !== null && !Number.isFinite(before)) throw new HttpError(400, "before must be a timestamp");
  const messages = await room(env, channelId).listMessages(Math.floor(limit), before);
  return json({ messages });
}

async function postMessage(request: Request, env: Env, user: PublicUser, channelId: string): Promise<Response> {
  await requireChannelMember(env, channelId, user);
  const body = asRecord(await readJson(request, 8_192));
  const text = asString(body.body, "Message");
  const result = await room(env, channelId).postMessage(
    {
      userId: user.id,
      username: user.username,
      displayName: user.displayName,
      avatarUrl: user.avatarUrl,
    },
    text,
  );
  if (!result.ok) throw new HttpError(400, result.error);
  return json({ message: result.message satisfies ChatMessage }, 201);
}

async function openSocket(request: Request, env: Env, user: PublicUser, channelId: string): Promise<Response> {
  if (request.headers.get("Upgrade") !== "websocket") {
    return new Response("Expected WebSocket", { status: 426 });
  }
  await requireChannelMember(env, channelId, user);
  const headers = new Headers(request.headers);
  for (const key of [...headers.keys()]) {
    if (key.toLowerCase().startsWith("x-hall-")) headers.delete(key);
  }
  headers.set("x-hall-user-id", user.id);
  headers.set("x-hall-username", user.username);
  headers.set("x-hall-display-name", user.displayName);
  if (user.avatarUrl) headers.set("x-hall-avatar-url", user.avatarUrl);
  return room(env, channelId).fetch(new Request(request, { headers }));
}

async function route(request: Request, env: Env, url: URL): Promise<Response> {
  const { pathname } = url;
  const method = request.method;
  await ensureReady(env);

  if (method === "GET" && pathname.startsWith("/api/avatars/")) {
    return getAvatar(env, pathname.slice("/api/avatars/".length));
  }

  if (method === "POST" && pathname === "/api/register") return register(request, env);
  if (method === "POST" && pathname === "/api/login") return login(request, env);
  if (method === "POST" && pathname === "/api/logout") {
    await destroySession(env, request);
    return json({ ok: true }, 200, clearSessionHeaders(request));
  }

  if (pathname === "/api/me" && method === "GET") {
    const user = await requireUser(env, request);
    return json({ user });
  }

  const user = await requireUser(env, request);

  if (pathname === "/api/me" && method === "PATCH") return updateProfile(request, env, user);
  if (pathname === "/api/me/avatar" && method === "PUT") return uploadAvatar(request, env, user);
  if (pathname === "/api/me/avatar" && method === "DELETE") return clearAvatar(env, user);

  const profileMatch = pathname.match(/^\/api\/users\/([^/]+)$/);
  if (profileMatch && method === "GET") return getProfile(env, decodeURIComponent(profileMatch[1] ?? ""));

  if (method === "GET" && pathname === "/api/servers") return listServers(env, user);
  if (method === "POST" && pathname === "/api/servers") return createServer(request, env, user);
  if (method === "POST" && pathname === "/api/join") return joinServer(request, env, user);

  const serverMatch = pathname.match(/^\/api\/servers\/([^/]+)(?:\/([^/]+))?$/);
  if (serverMatch) {
    const serverId = decodeURIComponent(serverMatch[1] ?? "");
    const action = serverMatch[2];
    if (!action && method === "GET") return serverDetail(env, user, serverId);
    if (action === "channels" && method === "POST") return createChannel(request, env, user, serverId);
    if (action === "leave" && method === "POST") return leaveServer(env, user, serverId);
  }

  const channelMatch = pathname.match(/^\/api\/channels\/([^/]+)\/(messages|websocket)$/);
  if (channelMatch) {
    const channelId = decodeURIComponent(channelMatch[1] ?? "");
    const action = channelMatch[2];
    if (action === "messages" && method === "GET") return listMessages(url, env, user, channelId);
    if (action === "messages" && method === "POST") return postMessage(request, env, user, channelId);
    if (action === "websocket" && method === "GET") return openSocket(request, env, user, channelId);
  }

  throw new HttpError(404, "Not found");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) {
      return new Response("Not found", { status: 404 });
    }
    if (request.method === "GET" && url.pathname === "/api/health") {
      try {
        await ensureReady(env);
      } catch (error) {
        console.error(
          JSON.stringify({
            event: "health_init_failed",
            message: error instanceof Error ? error.message : "unknown",
          }),
        );
      }
      return json({ ok: true, name: "Hall" });
    }
    try {
      return await route(request, env, url);
    } catch (error) {
      if (error instanceof HttpError) return json({ error: error.message }, error.status);
      console.error(
        JSON.stringify({
          event: "unhandled",
          message: error instanceof Error ? error.message : "unknown",
        }),
      );
      return json({ error: "Something went wrong" }, 500);
    }
  },
} satisfies ExportedHandler<Env>;
