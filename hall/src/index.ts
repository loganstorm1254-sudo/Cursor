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
  normalizeInviteCode,
  normalizePassword,
  normalizeServerName,
  normalizeUsername,
  POLL_PREFIX,
} from "./username";

export { ChannelRoom } from "./channel";
export { ServerHub } from "./hub";

const MAX_AVATAR_BYTES = 512_000;
const AVATAR_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

type ServerRow = {
  id: string;
  name: string;
  icon_letter: string;
  owner_id: string;
  invite_code: string;
  bio: string | null;
  avatar_key: string | null;
};

type ChannelRow = {
  id: string;
  server_id: string;
  name: string;
  position: number;
  owner_id: string;
};

function publicServer(row: ServerRow, userId: string, user?: PublicUser) {
  const isLobby = row.id === "lobby";
  const canManage = isLobby ? Boolean(user?.isPlatformOwner) : row.owner_id === userId;
  return {
    id: row.id,
    name: row.name,
    iconLetter: row.icon_letter,
    inviteCode: row.invite_code,
    inviteUrl: `https://hallchat.lopro.cc/invite/${encodeURIComponent(row.invite_code)}`,
    ownerId: row.owner_id,
    bio: row.bio ?? "",
    avatarUrl: row.avatar_key ? `/api/avatars/${encodeURIComponent(row.avatar_key)}` : null,
    isOwner: row.owner_id === userId,
    isLobby,
    canManage,
    unleavable: isLobby,
  };
}

function canManageServer(server: { id: string; owner_id: string }, user: PublicUser): boolean {
  if (server.id === "lobby") return user.isPlatformOwner;
  return server.owner_id === user.id;
}

async function memberOf(env: Env, serverId: string, userId: string): Promise<boolean> {
  const row = await env.DB.prepare("SELECT 1 AS ok FROM memberships WHERE server_id = ? AND user_id = ?")
    .bind(serverId, userId)
    .first<{ ok: number }>();
  return Boolean(row);
}

async function getChannel(env: Env, channelId: string): Promise<ChannelRow | null> {
  if (channelId.startsWith("dm:")) {
    const thread = await env.DB.prepare("SELECT id, user_a, user_b FROM dm_threads WHERE id = ?")
      .bind(channelId)
      .first<{ id: string; user_a: string; user_b: string }>();
    if (!thread) return null;
    return {
      id: thread.id,
      server_id: "dm",
      name: "dm",
      position: 0,
      owner_id: thread.user_a,
    };
  }
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
  if (channelId.startsWith("dm:")) {
    const thread = await env.DB.prepare("SELECT id, user_a, user_b FROM dm_threads WHERE id = ?")
      .bind(channelId)
      .first<{ id: string; user_a: string; user_b: string }>();
    if (!thread) throw new HttpError(404, "DM not found");
    if (thread.user_a !== user.id && thread.user_b !== user.id) {
      throw new HttpError(403, "That DM is not yours");
    }
    return {
      id: thread.id,
      server_id: "dm",
      name: "dm",
      position: 0,
      owner_id: thread.user_a,
    };
  }
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

function serverHub(env: Env, serverId: string) {
  return env.SERVERS.getByName(serverId);
}

async function listChannelRows(env: Env, serverId: string) {
  const channels = await env.DB.prepare(
    `SELECT id, name, position, COALESCE(kind, 'text') AS kind
     FROM channels
     WHERE server_id = ?
     ORDER BY CASE COALESCE(kind, 'text') WHEN 'voice' THEN 1 ELSE 0 END ASC, position ASC, name ASC`,
  )
    .bind(serverId)
    .all<{ id: string; name: string; position: number; kind: string }>();
  return channels.results ?? [];
}

async function publishServerChannels(env: Env, serverId: string): Promise<void> {
  const channels = await listChannelRows(env, serverId);
  try {
    await serverHub(env, serverId).fetch(
      new Request("https://hub/publish", {
        method: "POST",
        body: JSON.stringify({ type: "channels", channels }),
      }),
    );
  } catch (error) {
    console.error(
      JSON.stringify({
        event: "hub_publish_failed",
        serverId,
        message: error instanceof Error ? error.message : "unknown",
      }),
    );
  }
}

function dmThreadId(userA: string, userB: string): string {
  return userA < userB ? `dm:${userA}:${userB}` : `dm:${userB}:${userA}`;
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
        `INSERT OR IGNORE INTO memberships (server_id, user_id, joined_at, position)
         VALUES ('lobby', ?, ?, 0)`,
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
    `SELECT s.id, s.name, s.icon_letter, s.owner_id, s.invite_code, s.bio, s.avatar_key
     FROM memberships m
     JOIN servers s ON s.id = m.server_id
     WHERE m.user_id = ?
     ORDER BY m.position ASC, m.joined_at ASC`,
  )
    .bind(user.id)
    .all<ServerRow>();
  return json({ servers: (results ?? []).map((row) => publicServer(row, user.id, user)) });
}

async function reorderServers(request: Request, env: Env, user: PublicUser): Promise<Response> {
  const body = asRecord(await readJson(request, 8_192));
  const raw = body.serverIds;
  if (!Array.isArray(raw) || raw.length === 0) throw new HttpError(400, "serverIds must be a non-empty list");
  const serverIds = raw.map((id, index) => {
    if (typeof id !== "string" || !id) throw new HttpError(400, `serverIds[${index}] must be a string`);
    return id;
  });
  const existing = await env.DB.prepare("SELECT server_id AS id FROM memberships WHERE user_id = ?")
    .bind(user.id)
    .all<{ id: string }>();
  const existingIds = new Set((existing.results ?? []).map((row) => row.id));
  if (serverIds.length !== existingIds.size || serverIds.some((id) => !existingIds.has(id))) {
    throw new HttpError(400, "serverIds must include every server you are in once");
  }
  await env.DB.batch(
    serverIds.map((id, position) =>
      env.DB.prepare("UPDATE memberships SET position = ? WHERE server_id = ? AND user_id = ?").bind(
        position,
        id,
        user.id,
      ),
    ),
  );
  return json({ ok: true, serverIds });
}

async function updateServer(request: Request, env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare(
    "SELECT id, name, icon_letter, owner_id, invite_code, bio, avatar_key FROM servers WHERE id = ?",
  )
    .bind(serverId)
    .first<ServerRow>();
  if (!server) throw new HttpError(404, "Server not found");
  if (!(await memberOf(env, server.id, user.id))) throw new HttpError(403, "You are not in this server");
  if (!canManageServer(server, user)) {
    throw new HttpError(403, server.id === "lobby" ? "Only the Hall owner can edit Hall Official" : "Only the server owner can edit this server");
  }

  const body = asRecord(await readJson(request, 4_096));
  let name = server.name;
  let bio = server.bio ?? "";
  let invite = server.invite_code;
  let letter = server.icon_letter;

  if (body.name !== undefined) {
    const next = normalizeServerName(asString(body.name, "Server name"));
    if (!next) throw new HttpError(400, "Server names are 1–80 characters");
    if (server.id === "lobby" && next !== "Hall Official") {
      // Owner may restyle Hall Official but keep the brand name.
      name = "Hall Official";
    } else {
      name = next;
    }
    letter = iconLetter(name);
  }
  if (body.bio !== undefined) {
    const parsed = normalizeBio(asString(body.bio, "Bio"));
    if (typeof parsed !== "string") throw new HttpError(400, parsed.error);
    bio = parsed;
  }
  if (body.inviteCode !== undefined) {
    if (server.id === "lobby") throw new HttpError(400, "Hall Official invite stays hall");
    const next = normalizeInviteCode(asString(body.inviteCode, "Invite"));
    if (!next) throw new HttpError(400, "Invite codes are 3–32 letters, numbers, or hyphens");
    invite = next;
  }

  try {
    await env.DB.prepare(
      `UPDATE servers SET name = ?, icon_letter = ?, bio = ?, invite_code = ? WHERE id = ?`,
    )
      .bind(name, letter, bio, invite, server.id)
      .run();
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.includes("invite_code") || message.includes("UNIQUE")) {
      throw new HttpError(409, "That invite code is already taken");
    }
    throw error;
  }

  const updated = await env.DB.prepare(
    "SELECT id, name, icon_letter, owner_id, invite_code, bio, avatar_key FROM servers WHERE id = ?",
  )
    .bind(server.id)
    .first<ServerRow>();
  if (!updated) throw new HttpError(404, "Server not found");
  return json({ server: publicServer(updated, user.id, user) });
}

async function uploadServerAvatar(request: Request, env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare(
    "SELECT id, name, icon_letter, owner_id, invite_code, bio, avatar_key FROM servers WHERE id = ?",
  )
    .bind(serverId)
    .first<ServerRow>();
  if (!server) throw new HttpError(404, "Server not found");
  if (!(await memberOf(env, server.id, user.id))) throw new HttpError(403, "You are not in this server");
  if (!canManageServer(server, user)) throw new HttpError(403, "Only the server owner can change the icon");

  const type = (request.headers.get("content-type") ?? "").split(";")[0]?.trim().toLowerCase() ?? "";
  if (!AVATAR_TYPES.has(type)) throw new HttpError(415, "Use a JPEG, PNG, WebP, or GIF image");
  const bytes = await request.arrayBuffer();
  if (bytes.byteLength === 0) throw new HttpError(400, "Empty image");
  if (bytes.byteLength > MAX_AVATAR_BYTES) throw new HttpError(413, "Image must be under 512KB");

  const key = `servers/${server.id}/${crypto.randomUUID()}`;
  await env.AVATARS.put(key, bytes, {
    httpMetadata: { contentType: type, cacheControl: "public, max-age=31536000, immutable" },
  });
  await env.DB.prepare(`UPDATE servers SET avatar_key = ? WHERE id = ?`).bind(key, server.id).run();
  if (server.avatar_key && server.avatar_key !== key) {
    try {
      await env.AVATARS.delete(server.avatar_key);
    } catch {
      // Best-effort cleanup.
    }
  }
  const updated = await env.DB.prepare(
    "SELECT id, name, icon_letter, owner_id, invite_code, bio, avatar_key FROM servers WHERE id = ?",
  )
    .bind(server.id)
    .first<ServerRow>();
  if (!updated) throw new HttpError(404, "Server not found");
  return json({ server: publicServer(updated, user.id, user) });
}

async function nextMembershipPosition(env: Env, userId: string): Promise<number> {
  const row = await env.DB.prepare(
    "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM memberships WHERE user_id = ?",
  )
    .bind(userId)
    .first<{ next: number }>();
  return row?.next ?? 0;
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
    const position = await nextMembershipPosition(env, user.id);
    try {
      await env.DB.batch([
        env.DB.prepare(
          `INSERT INTO servers (id, name, icon_letter, owner_id, invite_code, created_at, bio)
           VALUES (?, ?, ?, ?, ?, ?, '')`,
        ).bind(serverId, name, iconLetter(name), user.id, inviteCode, now),
        env.DB.prepare(
          `INSERT INTO channels (id, server_id, name, position, created_at, kind)
           VALUES (?, ?, 'general', 0, ?, 'text')`,
        ).bind(channelId, serverId, now),
        env.DB.prepare(
          `INSERT INTO memberships (server_id, user_id, joined_at, position)
           VALUES (?, ?, ?, ?)`,
        ).bind(serverId, user.id, now, position),
      ]);
      console.log(JSON.stringify({ event: "server_created", serverId, userId: user.id }));
      return json(
        {
          server: publicServer(
            {
              id: serverId,
              name,
              icon_letter: iconLetter(name),
              owner_id: user.id,
              invite_code: inviteCode,
              bio: "",
              avatar_key: null,
            },
            user.id,
            user,
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
  if (!/^[a-z0-9-]{2,32}$/.test(code)) throw new HttpError(400, "That invite code is not valid");
  const server = await env.DB.prepare(
    "SELECT id, name, icon_letter, owner_id, invite_code, bio, avatar_key FROM servers WHERE invite_code = ?",
  )
    .bind(code)
    .first<ServerRow>();
  if (!server) throw new HttpError(404, "No server uses that invite");
  const already = await memberOf(env, server.id, user.id);
  if (!already) {
    const position = await nextMembershipPosition(env, user.id);
    await env.DB.prepare(
      `INSERT INTO memberships (server_id, user_id, joined_at, position)
       VALUES (?, ?, ?, ?)`,
    )
      .bind(server.id, user.id, Date.now(), position)
      .run();
  }
  return json({ server: publicServer(server, user.id, user) });
}

async function serverDetail(env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare(
    "SELECT id, name, icon_letter, owner_id, invite_code, bio, avatar_key FROM servers WHERE id = ?",
  )
    .bind(serverId)
    .first<ServerRow>();
  if (!server) throw new HttpError(404, "Server not found");
  if (!(await memberOf(env, server.id, user.id))) throw new HttpError(403, "You are not in this server");

  const channels = await listChannelRows(env, server.id);
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
    server: publicServer(server, user.id, user),
    channels,
    members: (members.results ?? []).map((member) => {
      const profile = toPublicUser(member);
      return {
        ...profile,
        isOwner: member.id === server.owner_id,
      };
    }),
  });
}

async function openServerHub(request: Request, env: Env, user: PublicUser, serverId: string): Promise<Response> {
  if (request.headers.get("Upgrade") !== "websocket") {
    return new Response("Expected WebSocket", { status: 426 });
  }
  if (!(await memberOf(env, serverId, user.id))) throw new HttpError(403, "You are not in this server");
  const headers = new Headers(request.headers);
  headers.set("x-hall-user-id", user.id);
  return serverHub(env, serverId).fetch(new Request(request, { headers }));
}

async function createChannel(request: Request, env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare("SELECT id, owner_id FROM servers WHERE id = ?")
    .bind(serverId)
    .first<{ id: string; owner_id: string }>();
  if (!server) throw new HttpError(404, "Server not found");
  if (!(await memberOf(env, server.id, user.id))) throw new HttpError(403, "You are not in this server");
  if (!canManageServer(server, user)) {
    throw new HttpError(403, server.id === "lobby" ? "Only the Hall owner can edit Hall Official" : "Only the server owner can add channels");
  }

  const body = asRecord(await readJson(request, 2_048));
  const name = normalizeChannelName(asString(body.name, "Channel name"));
  if (!name) throw new HttpError(400, "Channel names use letters, numbers, and hyphens");
  const kindRaw = body.kind === undefined ? "text" : asString(body.kind, "Channel type").toLowerCase();
  if (kindRaw !== "text" && kindRaw !== "voice") throw new HttpError(400, "Channel type must be text or voice");
  const kind = kindRaw;

  const positionRow = await env.DB.prepare(
    "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM channels WHERE server_id = ?",
  )
    .bind(server.id)
    .first<{ next: number }>();
  const channelId = crypto.randomUUID();
  const now = Date.now();
  try {
    await env.DB.prepare(
      `INSERT INTO channels (id, server_id, name, position, created_at, kind)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
      .bind(channelId, server.id, name, positionRow?.next ?? 0, now, kind)
      .run();
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.includes("UNIQUE")) throw new HttpError(409, "That channel already exists");
    throw error;
  }
  await publishServerChannels(env, server.id);
  return json({ channel: { id: channelId, name, position: positionRow?.next ?? 0, kind } }, 201);
}

async function reorderChannels(request: Request, env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare("SELECT id, owner_id FROM servers WHERE id = ?")
    .bind(serverId)
    .first<{ id: string; owner_id: string }>();
  if (!server) throw new HttpError(404, "Server not found");
  if (!(await memberOf(env, server.id, user.id))) throw new HttpError(403, "You are not in this server");
  if (!canManageServer(server, user)) {
    throw new HttpError(403, server.id === "lobby" ? "Only the Hall owner can edit Hall Official" : "Only the server owner can reorder channels");
  }

  const body = asRecord(await readJson(request, 8_192));
  const raw = body.channelIds;
  if (!Array.isArray(raw) || raw.length === 0) throw new HttpError(400, "channelIds must be a non-empty list");
  const channelIds = raw.map((id, index) => {
    if (typeof id !== "string" || !id) throw new HttpError(400, `channelIds[${index}] must be a string`);
    return id;
  });

  const existing = await env.DB.prepare("SELECT id FROM channels WHERE server_id = ?")
    .bind(server.id)
    .all<{ id: string }>();
  const existingIds = new Set((existing.results ?? []).map((row) => row.id));
  if (channelIds.length !== existingIds.size || channelIds.some((id) => !existingIds.has(id))) {
    throw new HttpError(400, "channelIds must include every channel in the server once");
  }

  await env.DB.batch(
    channelIds.map((id, position) =>
      env.DB.prepare("UPDATE channels SET position = ? WHERE id = ? AND server_id = ?").bind(position, id, server.id),
    ),
  );
  await publishServerChannels(env, server.id);
  return json({ ok: true, channelIds });
}

async function deleteChannel(env: Env, user: PublicUser, channelId: string): Promise<Response> {
  const channel = await getChannel(env, channelId);
  if (!channel) throw new HttpError(404, "Channel not found");
  if (!(await memberOf(env, channel.server_id, user.id))) throw new HttpError(403, "You are not in this server");
  if (!canManageServer({ id: channel.server_id, owner_id: channel.owner_id }, user)) {
    throw new HttpError(
      403,
      channel.server_id === "lobby" ? "Only the Hall owner can edit Hall Official" : "Only the server owner can delete channels",
    );
  }
  const kindRow = await env.DB.prepare(`SELECT COALESCE(kind, 'text') AS kind FROM channels WHERE id = ?`)
    .bind(channel.id)
    .first<{ kind: string }>();
  const kind = kindRow?.kind ?? "text";
  if (kind === "text") {
    const textCount = await env.DB.prepare(
      `SELECT COUNT(*) AS n FROM channels WHERE server_id = ? AND COALESCE(kind, 'text') = 'text'`,
    )
      .bind(channel.server_id)
      .first<{ n: number }>();
    if ((textCount?.n ?? 0) <= 1) throw new HttpError(400, "Keep at least one text channel");
  } else {
    const count = await env.DB.prepare("SELECT COUNT(*) AS n FROM channels WHERE server_id = ?")
      .bind(channel.server_id)
      .first<{ n: number }>();
    if ((count?.n ?? 0) <= 1) throw new HttpError(400, "Keep at least one channel");
  }
  await env.DB.prepare("DELETE FROM channels WHERE id = ?").bind(channel.id).run();
  await publishServerChannels(env, channel.server_id);
  return json({ ok: true, channelId: channel.id });
}

async function leaveServer(env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare("SELECT id, owner_id FROM servers WHERE id = ?")
    .bind(serverId)
    .first<{ id: string; owner_id: string }>();
  if (!server) throw new HttpError(404, "Server not found");
  if (server.id === "lobby") throw new HttpError(400, "Hall Official cannot be left");
  if (server.owner_id === user.id) {
    throw new HttpError(400, "Owners must delete the server instead of leaving");
  }
  await env.DB.prepare("DELETE FROM memberships WHERE server_id = ? AND user_id = ?").bind(server.id, user.id).run();
  return json({ ok: true });
}

async function deleteServer(env: Env, user: PublicUser, serverId: string): Promise<Response> {
  const server = await env.DB.prepare("SELECT id, owner_id FROM servers WHERE id = ?")
    .bind(serverId)
    .first<{ id: string; owner_id: string }>();
  if (!server) throw new HttpError(404, "Server not found");
  if (server.id === "lobby") throw new HttpError(400, "Hall Official cannot be deleted");
  if (server.owner_id !== user.id && !user.isPlatformOwner) {
    throw new HttpError(403, "Only the owner can delete this server");
  }
  const channels = await env.DB.prepare("SELECT id FROM channels WHERE server_id = ?")
    .bind(server.id)
    .all<{ id: string }>();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM memberships WHERE server_id = ?").bind(server.id),
    env.DB.prepare("DELETE FROM channels WHERE server_id = ?").bind(server.id),
    env.DB.prepare("DELETE FROM servers WHERE id = ?").bind(server.id),
  ]);
  // Best-effort: drop Durable Object message history is tied to channel ids; unused rooms expire.
  void channels;
  return json({ ok: true, serverId: server.id });
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

function encodePollBody(question: string, options: string[]): string {
  return `${POLL_PREFIX}${JSON.stringify({ question, options, votes: {} as Record<string, string[]> })}`;
}

function parsePollCommand(raw: string): { question: string; options: string[] } | null {
  const trimmed = raw.trim();
  if (!trimmed.toLowerCase().startsWith("/poll")) return null;
  const rest = trimmed.slice(5).trim();
  if (!rest) return null;
  const parts = rest.split("|").map((part) => part.trim()).filter(Boolean);
  if (parts.length < 3) return null;
  const [question, ...options] = parts;
  if (!question || options.length < 2 || options.length > 8) return null;
  if (question.length > 200 || options.some((opt) => opt.length > 80)) return null;
  return { question, options };
}

async function postMessage(request: Request, env: Env, user: PublicUser, channelId: string): Promise<Response> {
  await requireChannelMember(env, channelId, user);
  const body = asRecord(await readJson(request, 8_192));
  const text = asString(body.body, "Message");
  const poll = parsePollCommand(text);
  const payload = poll ? encodePollBody(poll.question, poll.options) : text;
  const result = await room(env, channelId).postMessage(
    {
      userId: user.id,
      username: user.username,
      displayName: user.displayName,
      avatarUrl: user.avatarUrl,
    },
    payload,
  );
  if (!result.ok) throw new HttpError(400, result.error);
  if (channelId.startsWith("dm:")) {
    await env.DB.prepare(`UPDATE dm_threads SET updated_at = ? WHERE id = ?`).bind(Date.now(), channelId).run();
  }
  return json({ message: result.message satisfies ChatMessage }, 201);
}

async function votePoll(request: Request, env: Env, user: PublicUser, channelId: string): Promise<Response> {
  await requireChannelMember(env, channelId, user);
  const body = asRecord(await readJson(request, 2_048));
  const messageId = asString(body.messageId, "messageId");
  const optionIndex = Number(body.optionIndex);
  if (!Number.isInteger(optionIndex) || optionIndex < 0) throw new HttpError(400, "Bad option");
  const result = await room(env, channelId).votePoll(user.id, messageId, optionIndex);
  if (!result.ok) throw new HttpError(400, result.error);
  return json({ message: result.message });
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
  headers.set("x-hall-channel-id", channelId);
  if (channelId.startsWith("dm:")) {
    headers.set("x-hall-server-id", "dm");
  } else {
    const channel = await getChannel(env, channelId);
    if (channel?.server_id) headers.set("x-hall-server-id", channel.server_id);
  }
  if (user.avatarUrl) headers.set("x-hall-avatar-url", user.avatarUrl);
  return room(env, channelId).fetch(new Request(request, { headers }));
}

async function listFriends(env: Env, user: PublicUser): Promise<Response> {
  const accepted = await env.DB.prepare(
    `SELECT u.id, u.username, u.display_name, u.bio, u.avatar_key, u.role
     FROM friends f
     JOIN users u ON u.id = f.friend_id
     WHERE f.user_id = ? AND f.status = 'accepted'
     ORDER BY u.display_name COLLATE NOCASE ASC`,
  )
    .bind(user.id)
    .all();
  const incoming = await env.DB.prepare(
    `SELECT u.id, u.username, u.display_name, u.bio, u.avatar_key, u.role, f.created_at
     FROM friends f
     JOIN users u ON u.id = f.user_id
     WHERE f.friend_id = ? AND f.status = 'pending'
     ORDER BY f.created_at DESC`,
  )
    .bind(user.id)
    .all();
  const outgoing = await env.DB.prepare(
    `SELECT u.id, u.username, u.display_name, u.bio, u.avatar_key, u.role, f.created_at
     FROM friends f
     JOIN users u ON u.id = f.friend_id
     WHERE f.user_id = ? AND f.status = 'pending'
     ORDER BY f.created_at DESC`,
  )
    .bind(user.id)
    .all();
  return json({
    friends: (accepted.results ?? []).map((row) => toPublicUser(row as never)),
    incoming: (incoming.results ?? []).map((row) => toPublicUser(row as never)),
    outgoing: (outgoing.results ?? []).map((row) => toPublicUser(row as never)),
  });
}

async function requestFriend(request: Request, env: Env, user: PublicUser): Promise<Response> {
  const body = asRecord(await readJson(request, 2_048));
  const parsed = normalizeUsername(asString(body.username, "Username"));
  if ("error" in parsed) throw new HttpError(400, parsed.error);
  if (parsed.username === user.username) throw new HttpError(400, "You cannot friend yourself");
  const peer = await findUserByUsername(env, parsed.username);
  if (!peer || peer.id === "system") throw new HttpError(404, "User not found");

  const existing = await env.DB.prepare(
    `SELECT status FROM friends WHERE user_id = ? AND friend_id = ?`,
  )
    .bind(user.id, peer.id)
    .first<{ status: string }>();
  if (existing?.status === "accepted") throw new HttpError(409, "Already friends");
  if (existing?.status === "pending") throw new HttpError(409, "Friend request already sent");

  const reverse = await env.DB.prepare(
    `SELECT status FROM friends WHERE user_id = ? AND friend_id = ?`,
  )
    .bind(peer.id, user.id)
    .first<{ status: string }>();
  const now = Date.now();
  if (reverse?.status === "pending") {
    await env.DB.batch([
      env.DB.prepare(`UPDATE friends SET status = 'accepted' WHERE user_id = ? AND friend_id = ?`).bind(peer.id, user.id),
      env.DB.prepare(
        `INSERT INTO friends (user_id, friend_id, status, created_at) VALUES (?, ?, 'accepted', ?)
         ON CONFLICT(user_id, friend_id) DO UPDATE SET status = 'accepted'`,
      ).bind(user.id, peer.id, now),
    ]);
    return json({ ok: true, status: "accepted", user: toPublicUser(peer) });
  }

  await env.DB.prepare(
    `INSERT INTO friends (user_id, friend_id, status, created_at) VALUES (?, ?, 'pending', ?)
     ON CONFLICT(user_id, friend_id) DO UPDATE SET status = 'pending', created_at = excluded.created_at`,
  )
    .bind(user.id, peer.id, now)
    .run();
  return json({ ok: true, status: "pending", user: toPublicUser(peer) }, 201);
}

async function respondFriend(request: Request, env: Env, user: PublicUser, peerId: string): Promise<Response> {
  const body = asRecord(await readJson(request, 1_024));
  const action = asString(body.action, "action").toLowerCase();
  if (action !== "accept" && action !== "decline") throw new HttpError(400, "action must be accept or decline");
  const pending = await env.DB.prepare(
    `SELECT user_id FROM friends WHERE user_id = ? AND friend_id = ? AND status = 'pending'`,
  )
    .bind(peerId, user.id)
    .first<{ user_id: string }>();
  if (!pending) throw new HttpError(404, "No friend request from that user");
  if (action === "decline") {
    await env.DB.prepare(`DELETE FROM friends WHERE user_id = ? AND friend_id = ?`).bind(peerId, user.id).run();
    return json({ ok: true, status: "declined" });
  }
  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare(`UPDATE friends SET status = 'accepted' WHERE user_id = ? AND friend_id = ?`).bind(peerId, user.id),
    env.DB.prepare(
      `INSERT INTO friends (user_id, friend_id, status, created_at) VALUES (?, ?, 'accepted', ?)
       ON CONFLICT(user_id, friend_id) DO UPDATE SET status = 'accepted'`,
    ).bind(user.id, peerId, now),
  ]);
  return json({ ok: true, status: "accepted" });
}

async function removeFriend(env: Env, user: PublicUser, peerId: string): Promise<Response> {
  await env.DB.batch([
    env.DB.prepare(`DELETE FROM friends WHERE user_id = ? AND friend_id = ?`).bind(user.id, peerId),
    env.DB.prepare(`DELETE FROM friends WHERE user_id = ? AND friend_id = ?`).bind(peerId, user.id),
  ]);
  return json({ ok: true });
}

async function listDms(env: Env, user: PublicUser): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT t.id, t.updated_at,
            CASE WHEN t.user_a = ? THEN t.user_b ELSE t.user_a END AS peer_id
     FROM dm_threads t
     WHERE t.user_a = ? OR t.user_b = ?
     ORDER BY t.updated_at DESC`,
  )
    .bind(user.id, user.id, user.id)
    .all<{ id: string; updated_at: number; peer_id: string }>();
  const threads = [];
  for (const row of results ?? []) {
    const peer = await findUserById(env, row.peer_id);
    if (!peer) continue;
    threads.push({
      id: row.id,
      updatedAt: row.updated_at,
      user: toPublicUser(peer),
    });
  }
  return json({ threads });
}

async function openDm(request: Request, env: Env, user: PublicUser): Promise<Response> {
  const body = asRecord(await readJson(request, 2_048));
  let peerId = typeof body.userId === "string" ? body.userId : "";
  if (!peerId && body.username !== undefined) {
    const parsed = normalizeUsername(asString(body.username, "Username"));
    if ("error" in parsed) throw new HttpError(400, parsed.error);
    const peer = await findUserByUsername(env, parsed.username);
    if (!peer) throw new HttpError(404, "User not found");
    peerId = peer.id;
  }
  if (!peerId || peerId === user.id) throw new HttpError(400, "Pick someone else to DM");
  const peer = await findUserById(env, peerId);
  if (!peer || peer.id === "system") throw new HttpError(404, "User not found");

  const friendship = await env.DB.prepare(
    `SELECT status FROM friends WHERE user_id = ? AND friend_id = ? AND status = 'accepted'`,
  )
    .bind(user.id, peer.id)
    .first<{ status: string }>();
  if (!friendship) throw new HttpError(403, "Add them as a friend before DMing");

  const id = dmThreadId(user.id, peer.id);
  const [userA, userB] = user.id < peer.id ? [user.id, peer.id] : [peer.id, user.id];
  const now = Date.now();
  await env.DB.prepare(
    `INSERT INTO dm_threads (id, user_a, user_b, updated_at) VALUES (?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at`,
  )
    .bind(id, userA, userB, now)
    .run();
  return json({ thread: { id, updatedAt: now, user: toPublicUser(peer) } });
}

function hasSessionCookie(request: Request): boolean {
  const header = request.headers.get("cookie");
  if (!header) return false;
  return header.split(";").some((part) => part.trim().startsWith("hall_session="));
}

async function route(request: Request, env: Env, url: URL): Promise<Response> {
  const { pathname } = url;
  const method = request.method;

  // Logged-out boot hits /api/me with no cookie — answer 401 without schema init
  // so two people opening the site at once do not serialize on cold-start work.
  if (pathname === "/api/me" && method === "GET" && !hasSessionCookie(request)) {
    throw new HttpError(401, "Sign in to continue");
  }

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
  if (method === "PUT" && pathname === "/api/servers/order") return reorderServers(request, env, user);
  if (method === "POST" && pathname === "/api/join") return joinServer(request, env, user);

  if (method === "GET" && pathname === "/api/friends") return listFriends(env, user);
  if (method === "POST" && pathname === "/api/friends") return requestFriend(request, env, user);
  const friendMatch = pathname.match(/^\/api\/friends\/([^/]+)$/);
  if (friendMatch) {
    const peerId = decodeURIComponent(friendMatch[1] ?? "");
    if (method === "POST") return respondFriend(request, env, user, peerId);
    if (method === "DELETE") return removeFriend(env, user, peerId);
  }

  if (method === "GET" && pathname === "/api/dms") return listDms(env, user);
  if (method === "POST" && pathname === "/api/dms") return openDm(request, env, user);

  const serverMatch = pathname.match(/^\/api\/servers\/([^/]+)(?:\/([^/]+))?$/);
  if (serverMatch) {
    const serverId = decodeURIComponent(serverMatch[1] ?? "");
    const action = serverMatch[2];
    if (!action && method === "GET") return serverDetail(env, user, serverId);
    if (!action && method === "PATCH") return updateServer(request, env, user, serverId);
    if (!action && method === "DELETE") return deleteServer(env, user, serverId);
    if (action === "avatar" && method === "PUT") return uploadServerAvatar(request, env, user, serverId);
    if (action === "channels" && method === "POST") return createChannel(request, env, user, serverId);
    if (action === "channel-order" && method === "PUT") return reorderChannels(request, env, user, serverId);
    if (action === "leave" && method === "POST") return leaveServer(env, user, serverId);
    if (action === "websocket" && method === "GET") return openServerHub(request, env, user, serverId);
  }

  const channelOnly = pathname.match(/^\/api\/channels\/([^/]+)$/);
  if (channelOnly && method === "DELETE") {
    return deleteChannel(env, user, decodeURIComponent(channelOnly[1] ?? ""));
  }

  const channelMatch = pathname.match(/^\/api\/channels\/([^/]+)\/(messages|websocket|poll-vote)$/);
  if (channelMatch) {
    const channelId = decodeURIComponent(channelMatch[1] ?? "");
    const action = channelMatch[2];
    if (action === "messages" && method === "GET") return listMessages(url, env, user, channelId);
    if (action === "messages" && method === "POST") return postMessage(request, env, user, channelId);
    if (action === "poll-vote" && method === "POST") return votePoll(request, env, user, channelId);
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
