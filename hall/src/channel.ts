import { DurableObject } from "cloudflare:workers";

export type ChatMessage = {
  id: string;
  userId: string;
  username: string;
  displayName: string;
  body: string;
  createdAt: number;
};

export type PresenceUser = {
  userId: string;
  username: string;
  displayName: string;
};

type Attachment = PresenceUser;

type MessageRow = {
  id: string;
  user_id: string;
  username: string;
  display_name: string;
  body: string;
  created_at: number;
};

const COOLDOWN_MS = 250;
const MAX_BODY = 2000;

function toMessage(row: MessageRow): ChatMessage {
  return {
    id: row.id,
    userId: row.user_id,
    username: row.username,
    displayName: row.display_name,
    body: row.body,
    createdAt: row.created_at,
  };
}

export class ChannelRoom extends DurableObject<Env> {
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      this.ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          username TEXT NOT NULL,
          display_name TEXT NOT NULL,
          body TEXT NOT NULL,
          created_at INTEGER NOT NULL
        )
      `);
      this.ctx.storage.sql.exec(`
        CREATE INDEX IF NOT EXISTS messages_created_idx ON messages (created_at)
      `);
      this.ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS rate (
          user_id TEXT PRIMARY KEY,
          last_at INTEGER NOT NULL
        )
      `);
    });
    this.ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair("ping", "pong"));
  }

  async listMessages(limit: number, before: number | null): Promise<ChatMessage[]> {
    const capped = Math.min(Math.max(limit, 1), 100);
    const rows =
      before === null
        ? this.ctx.storage.sql
            .exec<MessageRow>(
              `SELECT id, user_id, username, display_name, body, created_at
               FROM messages
               ORDER BY created_at DESC
               LIMIT ?`,
              capped,
            )
            .toArray()
        : this.ctx.storage.sql
            .exec<MessageRow>(
              `SELECT id, user_id, username, display_name, body, created_at
               FROM messages
               WHERE created_at < ?
               ORDER BY created_at DESC
               LIMIT ?`,
              before,
              capped,
            )
            .toArray();
    return rows.reverse().map(toMessage);
  }

  async postMessage(author: PresenceUser, body: string): Promise<{ ok: true; message: ChatMessage } | { ok: false; error: string }> {
    const saved = this.insertMessage(author, body);
    if ("error" in saved) return { ok: false, error: saved.error };
    this.broadcast(JSON.stringify({ type: "message", message: saved }));
    return { ok: true, message: saved };
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }
    const userId = request.headers.get("x-hall-user-id") ?? "";
    const username = request.headers.get("x-hall-username") ?? "";
    const displayName = request.headers.get("x-hall-display-name") ?? "";
    if (!userId || !username || !displayName) {
      return new Response("Missing member", { status: 401 });
    }

    const [client, server] = Object.values(new WebSocketPair());
    if (!client || !server) return new Response("Could not open WebSocket", { status: 500 });
    const attachment: Attachment = { userId, username, displayName };
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment(attachment);

    const online = this.onlineUsers();
    server.send(JSON.stringify({ type: "ready", online }));
    this.broadcast(JSON.stringify({ type: "presence", online }), server);

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    if (typeof message !== "string" || message === "ping") return;
    let parsed: { type?: string; body?: string };
    try {
      parsed = JSON.parse(message) as { type?: string; body?: string };
    } catch {
      return;
    }
    if (parsed.type !== "message" || typeof parsed.body !== "string") return;
    const attachment = ws.deserializeAttachment() as Attachment | null;
    if (!attachment?.userId) {
      ws.close(1008, "Unauthorized");
      return;
    }
    const saved = this.insertMessage(attachment, parsed.body);
    if ("error" in saved) {
      ws.send(JSON.stringify({ type: "error", error: saved.error }));
      return;
    }
    this.broadcast(JSON.stringify({ type: "message", message: saved }));
  }

  async webSocketClose(ws: WebSocket): Promise<void> {
    const online = this.onlineUsers(ws);
    this.broadcast(JSON.stringify({ type: "presence", online }), ws);
  }

  async webSocketError(ws: WebSocket): Promise<void> {
    try {
      ws.close(1011, "Error");
    } catch {
      // The socket may already be gone.
    }
  }

  private insertMessage(author: PresenceUser, body: string): ChatMessage | { error: string } {
    const text = body.trim();
    if (!text) return { error: "Message is empty" };
    if (text.length > MAX_BODY) return { error: "Message is too long" };
    const now = Date.now();
    const previous = this.ctx.storage.sql
      .exec<{ last_at: number }>("SELECT last_at FROM rate WHERE user_id = ?", author.userId)
      .toArray()[0];
    if (previous && now - previous.last_at < COOLDOWN_MS) {
      return { error: "Slow down a little" };
    }
    const message: ChatMessage = {
      id: crypto.randomUUID(),
      userId: author.userId,
      username: author.username,
      displayName: author.displayName,
      body: text,
      createdAt: now,
    };
    this.ctx.storage.sql.exec(
      `INSERT INTO messages (id, user_id, username, display_name, body, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
      message.id,
      message.userId,
      message.username,
      message.displayName,
      message.body,
      message.createdAt,
    );
    this.ctx.storage.sql.exec(
      `INSERT INTO rate (user_id, last_at) VALUES (?, ?)
       ON CONFLICT(user_id) DO UPDATE SET last_at = excluded.last_at`,
      author.userId,
      now,
    );
    return message;
  }

  private onlineUsers(except?: WebSocket): PresenceUser[] {
    const seen = new Map<string, PresenceUser>();
    for (const socket of this.ctx.getWebSockets()) {
      if (socket === except || socket.readyState !== WebSocket.OPEN) continue;
      const attachment = socket.deserializeAttachment() as Attachment | null;
      if (!attachment?.userId) continue;
      seen.set(attachment.userId, attachment);
    }
    return [...seen.values()];
  }

  private broadcast(payload: string, except?: WebSocket): void {
    for (const socket of this.ctx.getWebSockets()) {
      if (socket === except || socket.readyState !== WebSocket.OPEN) continue;
      try {
        socket.send(payload);
      } catch (error) {
        console.error(
          JSON.stringify({
            event: "broadcast_failed",
            message: error instanceof Error ? error.message : "unknown",
          }),
        );
      }
    }
  }
}
