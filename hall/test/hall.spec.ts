import { env, exports } from "cloudflare:workers";
import { evictDurableObject } from "cloudflare:test";
import { describe, expect, it } from "vitest";

type UserBody = { user: { id: string; username: string; displayName: string } };
type ErrorBody = { error: string };
type ServerBody = { servers: Array<{ id: string; name: string; inviteCode: string }> };
type DetailBody = {
  server: { id: string; inviteCode: string; isOwner: boolean };
  channels: Array<{ id: string; name: string }>;
  members: Array<{ id: string; username: string }>;
};
type MessagesBody = { messages: Array<{ id: string; body: string; username: string }> };
type MessageBody = { message: { id: string; body: string } };

async function register(username: string, password = "correct-horse") {
  const response = await exports.default.fetch("http://hall.test/api/register", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const body = (await response.json()) as UserBody & ErrorBody;
  const cookie = response.headers.get("set-cookie")?.split(";")[0] ?? "";
  return { response, body, cookie };
}

function authed(cookie: string, path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("cookie", cookie);
  return exports.default.fetch(`http://hall.test${path}`, { ...init, headers });
}

describe("Hall", () => {
  it("answers a health check", async () => {
    const response = await exports.default.fetch("http://hall.test/api/health");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true, name: "Hall" });
  });

  it("keeps @admin and @owner reserved and gives every other username away once", async () => {
    for (const username of ["admin", "@admin", "ADMIN", "owner", "@Owner"]) {
      const { response, body } = await register(username);
      expect(response.status).toBe(403);
      expect(body.error).toMatch(/reserved/i);
    }

    const first = await register("Logan");
    expect(first.response.status).toBe(201);
    expect(first.body.user).toMatchObject({ username: "logan", displayName: "Logan" });
    expect(first.cookie).toMatch(/^hall_session=/);

    const second = await register("logan");
    expect(second.response.status).toBe(409);

    const me = await authed(first.cookie, "/api/me");
    expect(me.status).toBe(200);
    const meBody = (await me.json()) as UserBody;
    expect(meBody.user.displayName).toBe("Logan");
  });

  it("rejects a short password and a bad login", async () => {
    const short = await register("piper", "short");
    expect(short.response.status).toBe(400);

    const created = await register("piper");
    expect(created.response.status).toBe(201);
    const login = await exports.default.fetch("http://hall.test/api/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username: "piper", password: "wrong-password" }),
    });
    expect(login.status).toBe(401);
  });

  it("puts new people in the lobby and keeps channel history on its own object", async () => {
    const ada = await register("ada");
    const grace = await register("grace");
    expect(ada.response.status).toBe(201);
    expect(grace.response.status).toBe(201);

    const servers = (await (await authed(ada.cookie, "/api/servers")).json()) as ServerBody;
    const lobby = servers.servers.find((server) => server.name === "Lobby");
    expect(lobby?.inviteCode).toBe("hall");

    const detail = (await (await authed(ada.cookie, `/api/servers/${lobby?.id}`)).json()) as DetailBody;
    const general = detail.channels.find((channel) => channel.name === "general");
    const random = detail.channels.find((channel) => channel.name === "random");
    expect(general?.id).toBe("lobby-general");
    expect(random?.id).toBe("lobby-random");

    const socketResponse = await authed(grace.cookie, `/api/channels/${general?.id}/websocket`, {
      headers: { Upgrade: "websocket", Connection: "Upgrade" },
    });
    expect(socketResponse.status).toBe(101);
    const socket = socketResponse.webSocket;
    expect(socket).toBeTruthy();
    if (!socket) return;
    socket.accept();
    const ready = new Promise<string>((resolve) => {
      socket.addEventListener("message", (event) => resolve(String(event.data)), { once: true });
    });
    expect(JSON.parse(await ready)).toMatchObject({ type: "ready" });

    const heard = new Promise<string>((resolve) => {
      socket.addEventListener("message", (event) => {
        const payload = JSON.parse(String(event.data)) as { type?: string };
        if (payload.type === "message") resolve(String(event.data));
      });
    });
    const posted = await authed(ada.cookie, `/api/channels/${general?.id}/messages`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body: "hello from ada" }),
    });
    expect(posted.status).toBe(201);
    expect(JSON.parse(await heard)).toMatchObject({
      type: "message",
      message: { body: "hello from ada", username: "ada" },
    });

    const echoed = new Promise<string>((resolve) => {
      socket.addEventListener("message", (event) => {
        const payload = JSON.parse(String(event.data)) as { type?: string; message?: { body?: string } };
        if (payload.type === "message" && payload.message?.body === "hello from grace") resolve(String(event.data));
      });
    });
    socket.send(JSON.stringify({ type: "message", body: "hello from grace" }));
    expect(JSON.parse(await echoed)).toMatchObject({ message: { username: "grace" } });

    const history = (await (await authed(ada.cookie, `/api/channels/${general?.id}/messages`)).json()) as MessagesBody;
    expect(history.messages.map((message) => message.body)).toEqual(["hello from ada", "hello from grace"]);

    const stub = env.CHANNELS.getByName(general?.id ?? "");
    await evictDurableObject(stub);
    const afterEvict = (await (await authed(ada.cookie, `/api/channels/${general?.id}/messages`)).json()) as MessagesBody;
    expect(afterEvict.messages.map((message) => message.body)).toEqual(["hello from ada", "hello from grace"]);

    const other = (await (await authed(ada.cookie, `/api/channels/${random?.id}/messages`)).json()) as MessagesBody;
    expect(other.messages).toEqual([]);
    socket.close(1000, "done");
  });

  it("bootstraps Rogue1254 as the platform owner and supports bios and avatars", async () => {
    const login = await exports.default.fetch("http://hall.test/api/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username: "Rogue1254", password: "rogue-owner-pass" }),
    });
    expect(login.status).toBe(200);
    const loginBody = (await login.json()) as UserBody & { user: { isPlatformOwner: boolean; bio: string } };
    expect(loginBody.user).toMatchObject({
      username: "rogue1254",
      displayName: "Rogue1254",
      isPlatformOwner: true,
    });
    const cookie = login.headers.get("set-cookie")?.split(";")[0] ?? "";

    const blockedRegister = await register("Rogue1254");
    expect(blockedRegister.response.status).toBe(403);

    const patched = await authed(cookie, "/api/me", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ bio: "Built Hall." }),
    });
    expect(patched.status).toBe(200);
    expect(((await patched.json()) as { user: { bio: string } }).user.bio).toBe("Built Hall.");

    const png = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="), (c) =>
      c.charCodeAt(0),
    );
    const uploaded = await authed(cookie, "/api/me/avatar", {
      method: "PUT",
      headers: { "content-type": "image/png" },
      body: png,
    });
    expect(uploaded.status).toBe(200);
    const uploadedBody = (await uploaded.json()) as { user: { avatarUrl: string | null } };
    expect(uploadedBody.user.avatarUrl).toMatch(/^\/api\/avatars\//);

    const avatar = await exports.default.fetch(`http://hall.test${uploadedBody.user.avatarUrl}`);
    expect(avatar.status).toBe(200);
    expect(avatar.headers.get("content-type")).toMatch(/image\/png/);
  });

  it("lets the owner add a channel and keeps strangers out until they use the invite", async () => {
    const ada = await register("ada_owner");
    const grace = await register("grace_guest");
    const created = await authed(ada.cookie, "/api/servers", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: "Ada Hall" }),
    });
    expect(created.status).toBe(201);
    const createdBody = (await created.json()) as { server: { id: string; inviteCode: string }; channel: { id: string } };

    const blocked = await authed(grace.cookie, `/api/channels/${createdBody.channel.id}/messages`);
    expect(blocked.status).toBe(403);

    const strangerChannel = await authed(grace.cookie, `/api/servers/${createdBody.server.id}/channels`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: "secret" }),
    });
    expect(strangerChannel.status).toBe(403);

    const added = await authed(ada.cookie, `/api/servers/${createdBody.server.id}/channels`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: "Plans" }),
    });
    expect(added.status).toBe(201);
    const addedBody = (await added.json()) as { channel: { name: string } };
    expect(addedBody.channel.name).toBe("plans");

    const joined = await authed(grace.cookie, "/api/join", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code: createdBody.server.inviteCode }),
    });
    expect(joined.status).toBe(200);

    const sent = await authed(grace.cookie, `/api/channels/${createdBody.channel.id}/messages`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body: "I made it in" }),
    });
    expect(sent.status).toBe(201);
    const sentBody = (await sent.json()) as MessageBody;
    expect(sentBody.message.body).toBe("I made it in");

    const leaveLobby = await authed(grace.cookie, "/api/servers/lobby/leave", { method: "POST" });
    expect(leaveLobby.status).toBe(400);
    expect(((await leaveLobby.json()) as ErrorBody).error).toMatch(/Lobby/i);

    const leaveOwned = await authed(ada.cookie, `/api/servers/${createdBody.server.id}/leave`, { method: "POST" });
    expect(leaveOwned.status).toBe(400);

    const left = await authed(grace.cookie, `/api/servers/${createdBody.server.id}/leave`, { method: "POST" });
    expect(left.status).toBe(200);
    const blockedAgain = await authed(grace.cookie, `/api/channels/${createdBody.channel.id}/messages`);
    expect(blockedAgain.status).toBe(403);
  });
});
